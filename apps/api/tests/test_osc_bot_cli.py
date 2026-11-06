"""CLI exercises MCP + separate storage transport without a human session file."""
import hashlib
import json
from unittest.mock import patch
import httpx
import pytest
from scripts.review_bot import ReviewClient, ReviewError, safe_output

@pytest.mark.parametrize('token',['','jwt.human.session','Bearer ffb_'+'A'*43])
def test_cli_refuses_human_sessions(token):
    with pytest.raises(ReviewError): ReviewClient('https://review.example.invalid',token)


def test_cli_streams_parts_and_waits_ready(tmp_path):
    media=tmp_path/'fixture.mp4';media.write_bytes(b'abcdef')
    client=ReviewClient('https://review.example.invalid','ffb_'+'A'*43)
    client.http.close();client.storage.close()
    calls=[];puts=[];states=iter([False,False,True])
    def mcp(request):
        body=json.loads(request.content)
        assert request.headers['Authorization']=='Bearer ffb_'+'A'*43
        method=body['method']
        if method=='initialize': result={}
        else:
            name=body['params']['name'];a=body['params']['arguments'];calls.append((name,a))
            if name=='upload_version':
                assert a['sha256']==hashlib.sha256(b'abcdef').hexdigest()
                value={'s3_key':'raw/fixture','upload_id':'fixture','asset_id':'asset1','version_id':'version1','chunk_size_bytes':3,'part_count':2}
            elif name=='presign_part': value={'presigned_url':'https://storage.example.invalid/part'+str(a['part_number'])+'?secret=fixture'}
            elif name=='complete_upload': value={'status':'processing'}
            else: value={'ready':next(states),'item_url':'https://review.example.invalid/projects/fixture/assets/asset1','version':{'processing_status':'processing'}}
            result={'isError':False,'content':[{'type':'text','text':json.dumps(value)}]}
        return httpx.Response(200,json={'jsonrpc':'2.0','id':body['id'],'result':result})
    def storage(request):
        assert 'authorization' not in request.headers
        puts.append(request.content)
        return httpx.Response(200,headers={'etag':'"fixture"'})
    client.http=httpx.Client(transport=httpx.MockTransport(mcp),headers={'Authorization':'Bearer ffb_'+'A'*43})
    client.storage=httpx.Client(transport=httpx.MockTransport(storage))
    with patch('scripts.review_bot.time.sleep'):
        client.initialize()
        result=client.upload('project1','01_SPOT',media)
    client.close()
    assert puts==[b'abc',b'def']
    assert [x[0] for x in calls].count('get_version')==3
    assert result['item_url'].endswith('/asset1')
    assert safe_output({'presigned_url':'secret','token':'secret'})=={'presigned_url':'[redacted]','token':'[redacted]'}


def test_cli_transport_failure_never_echoes_credentials():
    client=ReviewClient('https://review.example.invalid','ffb_'+'A'*43)
    client.http.close()
    def fail(request): raise httpx.ConnectError('sensitive http transport details',request=request)
    client.http=httpx.Client(transport=httpx.MockTransport(fail))
    with pytest.raises(ReviewError) as exc: client.initialize()
    client.close()
    assert 'sensitive' not in str(exc.value) and 'ffb_' not in str(exc.value)


def test_cli_retries_rate_limits_without_a_session_fallback():
    client=ReviewClient('https://review.example.invalid','ffb_'+'A'*43)
    client.http.close()
    replies=iter([httpx.Response(429,headers={'Retry-After':'1'}),httpx.Response(200,json={'result':{}})])
    client.http=httpx.Client(transport=httpx.MockTransport(lambda request:next(replies)))
    with patch('scripts.review_bot.time.sleep') as wait:
        client.initialize()
        wait.assert_called_once_with(1)
    client.close()
