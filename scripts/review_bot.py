#!/usr/bin/env python3
"""Review bot CLI: scoped MCP credentials only; never reads a human session file."""
import argparse
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlparse
import httpx

class ReviewError(Exception): pass

class ReviewClient:
    def __init__(self, base_url=None, token=None):
        self.base_url = (base_url or os.environ.get('REVIEW_BASE_URL', '')).rstrip('/')
        token = token or os.environ.get('REVIEW_BOT_TOKEN', '')
        host = urlparse(self.base_url)
        if host.scheme != 'https' and not (host.scheme == 'http' and host.hostname in ('127.0.0.1', 'localhost')):
            raise ReviewError('Set REVIEW_BASE_URL to the HTTPS Review origin')
        if host.username or host.password or host.query or host.fragment or host.path not in ('', '/'):
            raise ReviewError('REVIEW_BASE_URL must be an origin without credentials')
        if not re.fullmatch(r'ffb_[A-Za-z0-9_-]{43}', token):
            raise ReviewError('Set REVIEW_BOT_TOKEN to your own scoped bot token; human sessions are refused')
        self.http = httpx.Client(headers={'Authorization':'Bearer '+token, 'Accept':'application/json, text/event-stream',
                                          'MCP-Protocol-Version':'2025-06-18'}, timeout=300)
        # Storage PUTs must NEVER carry the Review authorization header.
        self.storage = httpx.Client(timeout=300, follow_redirects=False)
        self.sequence = 0

    def close(self):
        self.http.close(); self.storage.close()

    def rpc(self, method, params):
        self.sequence += 1
        try:
            for attempt in range(4):
                reply = self.http.post(self.base_url+'/mcp', json={'jsonrpc':'2.0','id':self.sequence,'method':method,'params':params})
                if reply.status_code != 429 or attempt == 3: break
                try: delay = max(1, min(60, int(reply.headers.get('Retry-After', '60'))))
                except ValueError: delay = 60
                time.sleep(delay)
            if reply.status_code != 200: raise ReviewError(f'Review refused request (HTTP {reply.status_code})')
            value = reply.json()
            if 'error' in value: raise ReviewError('Review protocol request failed')
            return value['result']
        except (httpx.HTTPError, ValueError, KeyError):
            raise ReviewError('Could not complete the Review request') from None

    def initialize(self):
        return self.rpc('initialize', {'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'review-bot','version':'0030'}})

    def call(self, name, **arguments):
        reply = self.rpc('tools/call', {'name':name,'arguments':arguments})
        if reply.get('isError'): raise ReviewError(reply['content'][0]['text'])
        return json.loads(reply['content'][0]['text'])

    def upload(self, project_id, item, path, new_item=False, timeout=1800):
        path = Path(path)
        checksum = hashlib.sha256()
        with path.open('rb') as source:
            for block in iter(lambda: source.read(1024*1024), b''): checksum.update(block)
        plan = self.call('upload_version', project_id=project_id, item=item, filename=path.name, sha256=checksum.hexdigest(),
                         file_size_bytes=path.stat().st_size, mime_type=mimetypes.guess_type(path.name)[0] or 'application/octet-stream', new_item=new_item)
        parts = []
        with path.open('rb') as source:
            for number in range(1, plan['part_count']+1):
                signed = self.call('presign_part', s3_key=plan['s3_key'], upload_id=plan['upload_id'], part_number=number)
                url = signed['presigned_url']
                parsed = urlparse(url)
                if parsed.scheme != 'https' and not (urlparse(self.base_url).hostname in ('127.0.0.1','localhost') and parsed.scheme=='http'):
                    raise ReviewError('Storage upload URL must use HTTPS')
                try:
                    response = self.storage.put(url, content=source.read(plan['chunk_size_bytes']))
                    if response.status_code not in (200,201): raise ReviewError('Storage refused an upload part')
                    etag = response.headers.get('etag')
                    if not etag: raise ReviewError('Storage did not return an upload receipt')
                except httpx.HTTPError:
                    raise ReviewError('Storage transfer failed; credentials and signed URLs are suppressed') from None
                parts.append({'PartNumber':number,'ETag':etag})
        self.call('complete_upload', s3_key=plan['s3_key'], upload_id=plan['upload_id'], asset_id=plan['asset_id'], version_id=plan['version_id'], parts=parts)
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            version = self.call('get_version', version_id=plan['version_id'])
            if version['ready']: return {'asset_id':plan['asset_id'],'version_id':plan['version_id'],'item_url':version['item_url']}
            if version['version']['processing_status']=='failed': raise ReviewError('Review processing failed')
            time.sleep(2)
        raise ReviewError(f'Upload completed; processing is still pending. Poll get_version for {plan["version_id"]}')


def safe_output(value):
    if isinstance(value, dict): return {k: ("[redacted]" if k in ("presigned_url", "token", "code") else safe_output(v)) for k,v in value.items()}
    if isinstance(value, list): return [safe_output(v) for v in value]
    return value

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    upload=sub.add_parser('upload')
    upload.add_argument('project_id'); upload.add_argument('item'); upload.add_argument('file')
    upload.add_argument('--new-item',action='store_true')
    action=sub.add_parser('call'); action.add_argument('tool'); action.add_argument('arguments',nargs='?',default='{}')
    args=parser.parse_args()
    client=None
    try:
        client=ReviewClient();client.initialize()
        result=client.upload(args.project_id,args.item,args.file,args.new_item) if args.command=='upload' else client.call(args.tool,**json.loads(args.arguments))
        print(json.dumps(safe_output(result),indent=2))
    except (ReviewError,OSError,ValueError) as exc:
        # Arbitrary OSError/JSON strings can contain private paths; only controlled ReviewError messages are shown.
        print(str(exc) if isinstance(exc,ReviewError) else 'Invalid input or unreadable upload file',file=sys.stderr)
        return 1
    finally:
        if client:client.close()
    return 0

if __name__=='__main__': raise SystemExit(main())
