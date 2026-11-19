import json, secrets, time, threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path
lock=threading.RLock(); users={}; reports=[]
class Handler(SimpleHTTPRequestHandler):
 def __init__(self,*a,**kw): super().__init__(*a,directory=str(Path(__file__).parent),**kw)
 def reply(self,data,status=200):
  b=json.dumps(data).encode(); self.send_response(status); self.send_header('Content-Type','application/json'); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(b)
 def do_POST(self):
  try:
   n=int(self.headers.get('Content-Length',0)); assert 0<n<100000; d=json.loads(self.rfile.read(n)); action=self.path
   with lock:
    now=time.time()
    for k in list(users):
     if now-users[k]['seen']>35: leave(k); users.pop(k,None)
    if action=='/join':
     role=d.get('role'); assert role in ('talk','listen'); k=secrets.token_urlsafe(32); users[k]={'role':role,'peer':None,'queue':[],'seen':now}; match(); return self.reply({'token':k})
    k=d.get('token'); u=users.get(k)
    if not u:return self.reply({'error':'Session expirée'},401)
    u['seen']=now
    if action=='/poll': q=u['queue']; u['queue']=[]; return self.reply({'events':q})
    if action=='/signal':
     p=users.get(u['peer']); assert p and d.get('room')==u.get('room'); p['queue'].append({'type':'signal','room':u['room'],'data':d['data']})
    elif action in ('/leave','/report'):
     if action=='/report': reports.append({'time':now,'room':u.get('room'),'reason':str(d.get('reason',''))[:500]}); Path('reports.jsonl').open('a').write(json.dumps(reports[-1])+'\n')
     leave(k); users.pop(k,None)
    else:return self.reply({'error':'Action inconnue'},404)
    return self.reply({'ok':True})
  except Exception:return self.reply({'error':'Requête invalide'},400)
 def do_GET(self):
  if urlparse(self.path).path not in ('/','/index.html','/manifest.json','/sw.js','/icon.svg'):return self.send_error(404)
  super().do_GET()
def leave(k):
 u=users.get(k); p=users.get(u.get('peer')) if u else None
 if p:p['peer']=None;p['role']='ended';p['queue'].append({'type':'ended'})
def match():
 a=[k for k,u in users.items() if u['role']=='talk' and not u['peer']];b=[k for k,u in users.items() if u['role']=='listen' and not u['peer']]
 for x,y in zip(a,b):
  room=secrets.token_hex(16)
  for k,p,offer in ((x,y,True),(y,x,False)):
   users[k].update(peer=p,room=room);users[k]['queue'].append({'type':'match','room':room,'offer':offer})
if __name__=='__main__':
 import os
 ThreadingHTTPServer(('0.0.0.0',int(os.getenv('PORT','8000'))),Handler).serve_forever()
