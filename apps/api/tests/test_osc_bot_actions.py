"""O25 integration contracts against an explicitly opted-in disposable Postgres."""
import hashlib
import os
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from apps.api.config import settings
from apps.api.database import get_db
from apps.api.models.user import User, UserStatus
from apps.api.models.project import Project, ProjectMember, ProjectRole
from apps.api.models.folder import Folder
from apps.api.models.asset import Asset, AssetType, AssetVersion, ProcessingStatus, MediaFile, FileType
from apps.api.models.comment import Comment
from apps.api.models.osc_bot import BotToken, BotRemoval, BotUpload
from apps.api.models.share import ShareLink
from apps.api.services.osc_bot_auth import issue, SCOPES, authenticate
from apps.api.services.osc_bot_operations import TOOLS, dispatch, verify_upload_bytes
from apps.api.services.auth_service import create_access_token
from apps.api.routers import osc_bot_actions, osc_bot_admin, comments

@pytest.fixture
def review(monkeypatch):
    url = os.getenv('OSC_REVIEW_TEST_DATABASE_URL')
    if not url: pytest.skip('requires explicit disposable OSC_REVIEW_TEST_DATABASE_URL')
    assert 'freeframe_test' in url, 'Only the disposable test database is allowed'
    monkeypatch.setattr(settings, 'osc_bot_access_enabled', True)
    engine = create_engine(url)
    with engine.connect() as conn:
        outer = conn.begin()
        db = Session(bind=conn, join_transaction_mode='create_savepoint')
        admin = User(id=uuid.uuid4(), email=f'{uuid.uuid4()}@example.invalid', name='Fixture admin', status=UserStatus.active, is_superadmin=True, email_verified=True)
        db.add(admin); db.flush()
        p = Project(name='fixture_job', created_by=admin.id)
        other = Project(name='fixture_other', created_by=admin.id)
        db.add_all([p, other]); db.flush()
        db.add(ProjectMember(project_id=p.id, user_id=admin.id, role=ProjectRole.owner))
        a = Asset(project_id=p.id, name='01_SPOT', asset_type=AssetType.video, created_by=admin.id)
        db.add(a); db.flush()
        v = AssetVersion(asset_id=a.id, version_number=1, created_by=admin.id, processing_status=ProcessingStatus.ready)
        db.add(v); db.flush()
        f = MediaFile(version_id=v.id, file_type=FileType.video, original_filename='spot_v1.mp4', mime_type='video/mp4', file_size_bytes=10,
                      s3_key_raw='raw/fixture', fps=23.976, duration_seconds=10)
        db.add(f)
        c = Comment(asset_id=a.id, version_id=v.id, author_id=admin.id, body='Fixture range note', timecode_start=1.0, timecode_end=2.0, visibility='internal')
        db.add(c); db.commit()
        db.execute(text('CREATE TABLE IF NOT EXISTS osc_version_labels (version_id uuid PRIMARY KEY, label text)'))
        db.execute(text('CREATE TABLE IF NOT EXISTS osc_version_tc (version_id uuid PRIMARY KEY, start_tc text, fps float, start_frames int, probed_at timestamptz DEFAULT now())'))
        db.execute(text('INSERT INTO osc_version_tc (version_id, start_tc, fps) VALUES (:v, :tc, :fps)'), {'v': str(v.id), 'tc': '00:59:55:00', 'fps': 23.976})
        db.execute(text('CREATE TABLE IF NOT EXISTS osc_guest_approvals (asset_id uuid)'))
        db.commit()
        with patch('apps.api.services.osc_bot_auth.rate_limit'), patch('apps.api.services.osc_timecode.probe_start_tc', return_value='00:59:55:00'), patch('apps.api.services.event_service.publish_sync'):
            token, value = issue(db, admin, 'fixture bot', list(SCOPES), [str(p.id)])
            app = FastAPI()
            app.include_router(osc_bot_actions.router); app.include_router(osc_bot_admin.router)
            app.dependency_overrides[get_db] = lambda: db
            client = TestClient(app)
            yield SimpleNamespace(db=db, client=client, admin=admin, project=p, other=other, asset=a, version=v, file=f, comment=c,
                                  token=token, value=value, headers={'Authorization': 'Bearer '+value},
                                  human={'Authorization': 'Bearer '+create_access_token(str(admin.id))})
        db.close(); outer.rollback()
    engine.dispose()

def call(r, tool, **args):
    return r.client.post('/osc/actions/'+tool, headers=r.headers, json={k:str(v) if isinstance(v, uuid.UUID) else v for k,v in args.items()})

def rpc(r, method, params=None, headers=None):
    return r.client.post('/mcp', headers=headers or r.headers, json={'jsonrpc':'2.0', 'id':1, 'method':method, 'params':params or {}})

def test_mcp_lifecycle_and_scoped_catalog(review):
    r=review
    assert rpc(r,'initialize', {'protocolVersion':'2025-06-18'}).json()['result']['serverInfo']['name']=='osc-review'
    assert rpc(r,'ping').json()['result']=={}
    tools=rpc(r,'tools/list').json()['result']['tools']
    assert {x['name'] for x in tools}==set(TOOLS)
    assert all(x['inputSchema']['additionalProperties'] is False for x in tools)
    assert r.client.post('/mcp', headers=r.headers, json={'jsonrpc':'2.0','method':'notifications/initialized'}).status_code==202
    assert r.client.get('/mcp').status_code==405
    assert r.client.delete('/mcp').status_code==405
    assert rpc(r,'bogus').json()['error']['code']==-32601
    assert rpc(r,'ping',headers={**r.headers,'Origin':'https://evil.invalid'}).status_code==403
    assert rpc(r,'ping',headers={**r.headers,'MCP-Protocol-Version':'invalid'}).status_code==400
    assert rpc(r,'ping',headers=r.human).status_code==401
    assert r.client.post('/mcp',json={}).status_code==401
    assert r.client.post('/mcp', headers={**r.headers,'Content-Type':'application/json'}, content=b'x'*65537).status_code==413


def test_revocation_over_http_and_no_bot_admin_session(review):
    r=review
    assert call(r,'list_projects').status_code==200
    for method,path,body in [('get','/osc/admin/bot-tokens',None),('post','/osc/admin/bot-tokens',{'name':'bad','scopes':['read']}),('get','/osc/admin/removals',None)]:
        response=r.client.request(method,path,headers=r.headers,json=body)
        assert response.status_code==401
    response=r.client.post(f'/osc/admin/bot-tokens/{r.token.id}/revoke',headers=r.human)
    assert response.status_code==200
    assert rpc(r,'ping').status_code==401
    assert call(r,'list_projects').status_code==401


def test_scope_project_and_extra_argument_refusals(review):
    r=review
    assert len(call(r,'list_projects').json())==1
    assert call(r,'list_assets',project_id=r.other.id).status_code==403
    r.token.scopes=['read'];r.db.commit()
    assert call(r,'create_folder',project_id=r.project.id,name='blocked').status_code==403
    assert call(r,'get_asset',asset_id=r.asset.id,override_links=['x']).status_code==422
    assert rpc(r,'tools/call',{'name':'create_folder','arguments':{'project_id':str(r.project.id),'name':'bad'}}).json()['result']['isError']


def test_read_tools_and_gui_parity(review):
    r=review
    for name,args in [('list_projects',{}),('list_folders',{'project_id':r.project.id}),('list_assets',{'project_id':r.project.id}),
                      ('get_asset',{'asset_id':r.asset.id}),('get_version',{'version_id':r.version.id}),('find_upload',{'filename':r.file.original_filename})]:
        assert call(r,name,**args).status_code==200,name
    catalog=r.client.get('/osc/actions/catalog',headers=r.human).json()
    assert {x['name'] for x in catalog}==set(TOOLS)
    assert all(x['gui'] for x in catalog)
    assert call(r,'get_version',version_id=r.version.id).json()['ready']


def test_organize_and_versions(review):
    r=review
    folder=call(r,'create_folder',project_id=r.project.id,name='Cuts').json()
    assert 'id' in folder,folder
    assert call(r,'rename_asset',asset_id=r.asset.id,name='01_NEW').status_code==200
    assert call(r,'rename_asset',asset_id=r.asset.id,name='01_NEW v2').status_code==422
    assert call(r,'move_asset',asset_id=r.asset.id,folder_id=folder['id']).status_code==200
    assert call(r,'bulk_move',project_id=r.project.id,asset_ids=[str(r.asset.id)],target_folder_id=None).status_code==200
    assert call(r,'set_version_label',version_id=r.version.id,label='v1 · option').status_code==200
    assert call(r,'get_version',version_id=r.version.id).json()['version']['osc_label']=='v1 · option'
    assert call(r,'create_project',stem='fixture_new',confirmed=True).status_code==403
    _,value=issue(r.db,r.admin,'all projects',['organize'])
    headers={'Authorization':'Bearer '+value}
    assert r.client.post('/osc/actions/create_project',headers=headers,json={'stem':'fixture_new'}).status_code==409
    assert r.client.post('/osc/actions/create_project',headers=headers,json={'stem':'fixture_new','confirmed':True}).status_code==200


def test_notes_timecode_and_export_match_gui(review):
    r=review
    result=call(r,'list_notes',version_id=r.version.id).json()
    note=result['notes'][0]
    assert note['in_frame']==24 and note['out_frame']==48
    assert note['in_tc']=='00:59:56:00' and note['out_tc']=='00:59:57:00'
    assert note['author_name']=='Fixture admin' and note['visibility']=='internal'
    ctx=authenticate(r.db,r.value)
    for format in ('edl','fcpxml','premiere_xml'):
        response=call(r,'export_notes',version_id=r.version.id,format=format)
        assert response.status_code==200,response.text
        gui=comments.export_comments(r.asset.id,format,r.version.id,None,None,True,r.db,ctx.actor)
        assert response.json()['content']==gui.body.decode()
    assert call(r,'export_notes',version_id=r.version.id,format='json').status_code==200
    assert call(r,'mark_note_addressed',comment_id=r.comment.id).json()['resolved'] is True
    assert call(r,'mark_note_addressed',comment_id=r.comment.id).json()['resolved'] is True
    assert call(r,'list_notes',version_id=r.version.id,status='open').json()['notes']==[]
    assert call(r,'reply_to_comment',comment_id=r.comment.id,body='forbidden').status_code==404


def test_archive_restore_and_enabled_ancestor_link_refusal(review):
    r=review
    archived=call(r,'archive_asset',asset_id=r.asset.id)
    assert archived.status_code==200,archived.text
    receipt=archived.json()['receipt_id']
    assert r.asset.folder_id is not None and r.asset.deleted_at is None
    assert call(r,'restore_archive',receipt_id=receipt).json()['restored']
    assert r.asset.folder_id is None
    parent=Folder(project_id=r.project.id,name='Parent',created_by=r.admin.id)
    r.db.add(parent);r.db.flush()
    child=Folder(project_id=r.project.id,name='Child',parent_id=parent.id,created_by=r.admin.id)
    r.db.add(child);r.db.flush();r.asset.folder_id=child.id
    link=ShareLink(token='fixture-'+str(uuid.uuid4()),folder_id=parent.id,created_by=r.admin.id,is_enabled=True)
    r.db.add(link);r.db.commit()
    assert call(r,'archive_asset',asset_id=r.asset.id).status_code==409
    assert call(r,'archive_folder',folder_id=parent.id).status_code==409
    assert call(r,'move_asset',asset_id=r.asset.id,folder_id=None).status_code==409
    link.is_enabled=False;r.db.commit()
    response=call(r,'archive_folder',folder_id=parent.id)
    assert response.status_code==200,response.text
    assert call(r,'restore_archive',receipt_id=response.json()['receipt_id']).status_code==200
    assert parent.parent_id is None and r.asset.deleted_at is None


def test_removal_human_confirmation_only_single_use_and_expiring(review):
    r=review
    response=call(r,'request_removal',target_type='asset',target_id=r.asset.id,reason='fixture cleanup')
    assert response.status_code==200,response.text
    ident=response.json()['request_id']
    assert r.asset.deleted_at is None
    path=f'/osc/admin/removals/{ident}'
    assert r.client.post(path+'/code',headers=r.headers).status_code==401
    assert r.client.post(path+'/confirm',headers=r.headers,json={'code':'made-up'}).status_code==401
    code=r.client.post(path+'/code',headers=r.human).json()['code']
    assert r.client.post(path+'/confirm',headers=r.human,json={'code':'wrong'}).status_code==409
    request=r.db.get(BotRemoval,uuid.UUID(ident))
    request.code_expires_at=datetime.now(timezone.utc)-timedelta(seconds=1);r.db.commit()
    assert r.client.post(path+'/confirm',headers=r.human,json={'code':code}).status_code==409
    code=r.client.post(path+'/code',headers=r.human).json()['code']
    assert r.client.post(path+'/confirm',headers=r.human,json={'code':code}).json()['trashed']
    assert r.asset.deleted_at is not None
    assert r.client.post(path+'/confirm',headers=r.human,json={'code':code}).status_code==409


def test_upload_new_stack_version_dedupe_and_hash_verification(review):
    r=review
    def begin(item,filename,sha,new_item=False):
        return call(r,'upload_version',project_id=r.project.id,item=item,filename=filename,sha256=sha,file_size_bytes=3,mime_type='video/mp4',new_item=new_item)
    with patch('apps.api.routers.upload.create_multipart_upload',return_value='fixture-multipart'),patch('apps.api.routers.upload.upload_guard_error',return_value=None):
        assert begin('MISSING','new.mp4','a'*64).status_code==409
        assert begin('BAD v2','new.mp4','a'*64,True).status_code==422
        response=begin('NEW','new.mp4',hashlib.sha256(b'abc').hexdigest(),True)
        assert response.status_code==200,response.text
        plan=response.json()
        assert plan['part_count']==1 and plan['state']=='uploading'
        assert begin('NEW','new.mp4','b'*64).status_code==409
        assert begin('ANOTHER','different.mp4',hashlib.sha256(b'abc').hexdigest(),True).status_code==409
        response=begin('NEW','next.mp4','c'*64)
        assert response.status_code==200,response.text
        assert response.json()['asset_id']==plan['asset_id']
        assert r.db.get(AssetVersion,uuid.UUID(response.json()['version_id'])).version_number==2
    with patch('apps.api.routers.upload.presign_upload_part',return_value='https://storage.invalid/fixture'):
        assert call(r,'presign_part',s3_key=plan['s3_key'],upload_id=plan['upload_id'],part_number=1).status_code==200
    v=r.db.get(AssetVersion,uuid.UUID(plan['version_id']))
    f=r.db.query(MediaFile).filter(MediaFile.version_id==v.id).one()
    r.db.info['osc_verify_upload']=True
    with patch('apps.api.services.s3_service.get_s3_client') as storage:
        body=storage.return_value.get_object.return_value['Body'];body.iter_chunks.return_value=[b'abc']
        verify_upload_bytes(r.db,v,f)
    assert r.db.query(BotUpload).filter_by(version_id=v.id).one().verified_at is not None
    second=r.db.get(AssetVersion,uuid.UUID(response.json()['version_id']))
    second_file=r.db.query(MediaFile).filter_by(version_id=second.id).one()
    with patch('apps.api.services.s3_service.get_s3_client') as storage:
        storage.return_value.get_object.return_value['Body'].iter_chunks.return_value=[b'wrong bytes']
        with pytest.raises(HTTPException) as exc: verify_upload_bytes(r.db,second,second_file)
        assert exc.value.status_code==409 and second.processing_status==ProcessingStatus.failed
    assert call(r,'find_upload',sha256=hashlib.sha256(b'abc').hexdigest()).json()[0]['version_id']==plan['version_id']


def test_merge_reuses_superadmin_service_and_refuses_client_links(review):
    r=review
    source=Asset(project_id=r.project.id,name='SOURCE',asset_type=AssetType.video,created_by=r.admin.id)
    r.db.add(source);r.db.flush()
    v=AssetVersion(asset_id=source.id,version_number=1,created_by=r.admin.id,processing_status=ProcessingStatus.ready)
    r.db.add(v);r.db.commit()
    response=call(r,'merge_into_stack',target_asset_id=r.asset.id,source_asset_ids=[str(source.id)],dry_run=True)
    assert response.status_code==200,response.text
    response=call(r,'merge_into_stack',target_asset_id=r.asset.id,source_asset_ids=[str(source.id)],dry_run=False)
    assert response.status_code==200,response.text
    r.db.refresh(v);r.db.refresh(source)
    assert v.asset_id==r.asset.id and source.folder_id is not None and source.deleted_at is None

@pytest.mark.parametrize('tool', list(TOOLS))
def test_every_tool_checks_its_scope(review, tool):
    r=review
    args={
        'project_id':str(r.project.id),'asset_id':str(r.asset.id),'version_id':str(r.version.id),
        'folder_id':str(uuid.uuid4()),'filename':'fixture.mp4','sha256':'a'*64,'item':'01_SPOT','file_size_bytes':3,
        'mime_type':'video/mp4','s3_key':'raw/fixture','upload_id':'fixture','part_number':1,'stem':'fixture_job',
        'name':'Fixture name','label':'Fixture label','target_asset_id':str(r.asset.id),'source_asset_ids':[str(r.asset.id)],
        'comment_id':str(r.comment.id),'target_type':'asset','target_id':str(r.asset.id),'reason':'Fixture cleanup','receipt_id':str(uuid.uuid4())}
    schema=TOOLS[tool][1]
    required={k:args[k] for k in schema.model_fields if schema.model_fields[k].is_required()}
    r.token.scopes=[];r.db.commit()
    assert call(r,tool,**required).status_code==403


def test_cannot_move_private_item_into_enabled_client_folder(review):
    r=review
    folder=Folder(project_id=r.project.id,name='Client delivery',created_by=r.admin.id)
    r.db.add(folder);r.db.flush()
    r.db.add(ShareLink(token='fixture-'+str(uuid.uuid4()),folder_id=folder.id,created_by=r.admin.id,is_enabled=True));r.db.commit()
    assert call(r,'move_asset',asset_id=r.asset.id,folder_id=folder.id).status_code==409
    assert call(r,'bulk_move',project_id=r.project.id,asset_ids=[str(r.asset.id)],target_folder_id=str(folder.id)).status_code==409
    assert r.asset.folder_id is None


def test_complete_upload_queues_worker_and_reports_ready(review):
    r=review
    with patch('apps.api.routers.upload.create_multipart_upload',return_value='fixture-multipart'),patch('apps.api.routers.upload.upload_guard_error',return_value=None):
        response=call(r,'upload_version',project_id=r.project.id,item='NEW',filename='complete.mp4',sha256=hashlib.sha256(b'abc').hexdigest(),file_size_bytes=3,mime_type='video/mp4',new_item=True)
    assert response.status_code==200,response.text
    plan=response.json()
    with patch('apps.api.routers.upload.list_upload_parts',return_value=[{'PartNumber':1,'Size':3,'ETag':'"fixture"'}]),patch('apps.api.routers.upload.complete_multipart_upload'),patch('apps.api.routers.upload.head_object_size',return_value=3),patch('apps.api.routers.upload._trigger_processing') as process,patch('apps.api.services.s3_service.get_s3_client') as storage:
        storage.return_value.get_object.return_value['Body'].iter_chunks.return_value=[b'abc']
        response=call(r,'complete_upload',**{k:plan[k] for k in ('s3_key','upload_id','asset_id','version_id')})
        assert response.status_code==200,response.text
        process.assert_called_once()
    assert call(r,'get_version',version_id=plan['version_id']).json()['ready'] is False
    v=r.db.get(AssetVersion,uuid.UUID(plan['version_id']));v.processing_status=ProcessingStatus.ready;r.db.commit()
    assert call(r,'get_version',version_id=plan['version_id']).json()['ready'] is True


def test_future_expiry_is_not_misread_in_database_timezone(review):
    r=review
    r.token.expires_at=datetime.now(timezone.utc)+timedelta(minutes=10);r.db.commit()
    assert rpc(r,'ping').status_code==200

@pytest.mark.parametrize('content,ready',[(b'abc',True),(b'wrong',False)])
def test_worker_never_transcodes_unverified_bot_bytes(review, content, ready):
    r=review
    from apps.api.tasks import transcode_tasks
    r.version.osc_content_sha256=hashlib.sha256(b'abc').hexdigest()
    r.db.add(BotUpload(version_id=r.version.id,filename='worker.mp4',sha256=r.version.osc_content_sha256));r.db.commit()
    version_id = r.version.id
    with patch.object(transcode_tasks,'SessionLocal',return_value=r.db),patch.object(transcode_tasks,'_process_video') as encoder,patch.object(transcode_tasks,'_publish_event'),patch('apps.api.services.s3_service.get_s3_client') as storage,patch.object(transcode_tasks,'get_s3_client'),patch.object(transcode_tasks.process_asset,'retry',side_effect=RuntimeError('fixture retry')):
        storage.return_value.get_object.return_value['Body'].iter_chunks.return_value=[content]
        if ready: transcode_tasks.process_asset.run(str(r.asset.id),str(r.version.id))
        else:
            with pytest.raises(RuntimeError,match='fixture retry'):transcode_tasks.process_asset.run(str(r.asset.id),str(r.version.id))
        assert encoder.called is ready
    v=r.db.get(AssetVersion,version_id)
    assert (v.processing_status==ProcessingStatus.ready) is ready
    fingerprint=r.db.query(BotUpload).filter_by(version_id=v.id).one()
    assert (fingerprint.verified_at is not None) is ready


def test_folder_bulk_move_cannot_cycle_through_gui_or_mcp(review):
    r=review
    from apps.api.routers import folders
    from apps.api.schemas.folder import BulkMoveRequest
    parent=Folder(project_id=r.project.id,name='Parent',created_by=r.admin.id)
    r.db.add(parent);r.db.flush()
    child=Folder(project_id=r.project.id,name='Child',parent_id=parent.id,created_by=r.admin.id)
    r.db.add(child);r.db.commit()
    assert call(r,'bulk_move',project_id=r.project.id,folder_ids=[str(parent.id)],target_folder_id=str(child.id)).status_code==400
    with pytest.raises(HTTPException) as exc:
        folders.bulk_move(r.project.id,BulkMoveRequest(folder_ids=[parent.id],target_folder_id=child.id),r.db,r.admin)
    assert exc.value.status_code==400
    assert parent.parent_id is None and child.parent_id==parent.id


def test_admin_gui_can_manage_a_project_created_by_a_bot(review):
    r=review
    _,value=issue(r.db,r.admin,'project creator',['organize'])
    response=r.client.post('/osc/actions/create_project',headers={'Authorization':'Bearer '+value},json={'stem':'fixture_bot_created','confirmed':True})
    assert response.status_code==200,response.text
    project_id=response.json()['id']
    assert r.client.post('/osc/actions/list_assets',headers=r.human,json={'project_id':project_id}).status_code==200
    assert r.client.post('/osc/actions/create_folder',headers=r.human,json={'project_id':project_id,'name':'Fixture folder'}).status_code==200
