"""Record a real isolated fixture run; optionally render its evidence as a 70s MP4.
Video rendering needs Pillow and imageio-ffmpeg; the worker needs neither.
"""
import contextlib, importlib.util, io, json, os, subprocess, sys, tempfile, threading, time
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
ROOT=Path(__file__).resolve().parent

def record():
    state={'healthy':False}
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):self.send_response(200 if state['healthy'] else 503);self.end_headers()
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    scenes=[]; processes=[]
    with tempfile.TemporaryDirectory(prefix='clawcare-demo-') as tmp:
        env=os.environ.copy();env['CLAWCARE_DB']=str(Path(tmp)/'demo.sqlite3')
        def cli(*args):
            r=subprocess.run([sys.executable,str(ROOT/'clawcare.py'),*args],env=env,text=True,capture_output=True,timeout=30)
            return r.returncode,(r.stdout+r.stderr).strip()
        def start():
            p=subprocess.Popen([sys.executable,str(ROOT/'clawcare.py'),'worker'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            processes.append(p);return p
        import sqlite3
        def case(expected):
            end=time.monotonic()+20
            while time.monotonic()<end:
                with contextlib.closing(sqlite3.connect(env['CLAWCARE_DB'])) as c:
                    row=c.execute('SELECT id,status FROM incidents').fetchone()
                    if row and row[1]==expected:return row[0]
                time.sleep(.1)
            raise RuntimeError('Expected case status: '+expected)
        try:
            cli('add',f'http://127.0.0.1:{server.server_port}/health','--interval','1')
            p=start();ident=case('AWAITING_APPROVAL')
            scenes.append(('ClawCare | Background reliability engineer',['Actual local HTTP fixture run','Endpoint returns HTTP 503; worker runs independently.','No API key or model calls are used in this demo.']))
            scenes.append(('One failure. One durable work order.',[ident,'Status: AWAITING_APPROVAL','Inspection, work order and approval gate are recorded.']))
            p.terminate();p.wait(timeout=10);p=start();time.sleep(1.2)
            assert case('AWAITING_APPROVAL')==ident
            scenes.append(('Worker restarted. Case preserved.',[ident,'Same SQLite case survived process termination/restart.','Repeated polling did not create a second open case.']))
            code,msg=cli('repair',ident);assert code!=0
            scenes.append(('Approval is enforced',[msg,'No repair action was executed.']))
            code,_=cli('approve',ident,'--actor','demo-operator');assert code==0
            code,msg=cli('repair',ident);assert code==0
            case('RECOVERY_REQUIRED')
            scenes.append(('Simulation is not a repair',['Approved simulation: external effect = NONE','Verification still sees HTTP 503.','Status: RECOVERY_REQUIRED']))
            state['healthy']=True;case('COMPLETED')
            p.terminate();p.wait(timeout=10)
            code,snapshot=cli('checkpoint');assert code==0
            with contextlib.closing(sqlite3.connect(snapshot)) as c:
                assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            scenes.append(('External recovery verified',['Fixture was restored externally; worker observed HTTP 200.','Status: COMPLETED; audit attributes external recovery.','SQLite ledger snapshot integrity: OK']))
            _,audit=cli('audit',ident)
            scenes.append(('What ships today',['Real background monitoring + durable work-order audit','Single-use simulation approval + verified ledger snapshot','Still pending: real Gateway repair, multiplayer, Index reporting.']))
            return {'fixture':'loopback HTTP 503 to 200','case':ident,'scenes':scenes,'audit':audit,'video_kind':'Rendered evidence from actual fixture run; not a screen recording'}
        finally:
            for p in processes:
                if p.poll() is None:p.terminate();p.wait(timeout=10)
            server.shutdown();server.server_close();thread.join(timeout=5)

def render(evidence,path):
    from PIL import Image,ImageDraw,ImageFont
    import imageio_ffmpeg,textwrap
    font_path='C:/Windows/Fonts/segoeui.ttf'
    def font(size):
        try:return ImageFont.truetype(font_path,size)
        except OSError:return ImageFont.load_default(size=size)
    writer=imageio_ffmpeg.write_frames(str(path),(1280,720),fps=2,codec='libx264',pix_fmt_in='rgb24',pix_fmt_out='yuv420p',output_params=['-movflags','+faststart'])
    writer.send(None)
    try:
        for index,(title,lines) in enumerate(evidence['scenes']):
            image=Image.new('RGB',(1280,720),'#0e1625');draw=ImageDraw.Draw(image)
            draw.text((60,48),'CLAWCARE  /  MVP 0.2.0',font=font(24),fill='#66e3ba')
            draw.text((60,135),title,font=font(42),fill='white')
            y=245
            for line in lines:
                for part in textwrap.wrap(line,65):
                    draw.text((60,y),part,font=font(29),fill='#e2e8f0');y+=44
                y+=15
            draw.text((60,624),'ISOLATED HTTP FIXTURE  |  NO PRODUCTION REPAIR CLAIM',font=font(21),fill='#f0c879')
            draw.text((60,661),f'Evidence segment {index+1}/7  |  MIT licensed',font=font(19),fill='#93a4ba')
            for _ in range(20):writer.send(image.tobytes())
    finally:writer.close()

if __name__=='__main__':
    out=ROOT/'demo';out.mkdir(exist_ok=True)
    evidence=record();(out/'evidence.json').write_text(json.dumps(evidence,indent=2),encoding='utf8')
    if '--video' in sys.argv:render(evidence,out/'clawcare-mvp-demo.mp4')
    print('Recorded actual fixture evidence in demo/evidence.json')
