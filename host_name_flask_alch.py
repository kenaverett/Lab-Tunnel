import os
import json
import time
import ConfigParser
from flask import Flask, request
from flask import Response
from flask_sqlalchemy import SQLAlchemy
import datetime
from threading import Timer
import time
import pwd
import getpass

REMOTE_USER = None
PORT = 5001

app = Flask(__name__)


DATABASE = 'vm_hosts.sqlite3'
__SECRET_KEY__ = '62cc35df-af28-48ea-a623-79910f6743f8'




if not REMOTE_USER:
    REMOTE_USER=getpass.getuser()


remote_user_home = os.path.expanduser('~'+REMOTE_USER)

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///vm_hosts.sqlite3'
db = SQLAlchemy(app)


class Host(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    host_name = db.Column(db.String(10), unique=True)
    ip_addr = db.Column(db.String(20), unique=True)
    host_id = db.Column(db.String(50))
    last_date = db.Column(db.Date)
    
    def __init__(self, host_name, ip_addr, host_id, last_date):
        
        self.host_name = host_name
        self.ip_addr = ip_addr
        self.host_id = host_id
        self.last_date = last_date

    def __repr__(self):
        return '<host: %r, ip: %r>' % (self.host_name, self.ip_addr) 

db.create_all()


@app.route('/gethosts/<secret_key>', methods=['GET'])
def get_hosts(secret_key):

    tmp_tbl='<style>table {border-collapse: collapse;}table, th, td {border: 1px solid black;}</style><table>'
    
    if secret_key==__SECRET_KEY__:
        tmp_tbl +='<table>'
        
        columns = Host.metadata.tables['host'].columns.keys()
        tmp_tbl += '<tr>'
        for col in columns:
            tmp_tbl +='<th>%s</th>' % col
        tmp_tbl +='</tr>\n'

        for host in Host.query.all():
            tmp_tbl += '<tr>'
            for col in columns:
                tmp_tbl +='<td>{}</td>'.format(getattr(host, col))
            tmp_tbl +='</tr>\n'
    else:
        tmp_tbl +='<tr><th>Check Secret Key</th></tr>\n'
    tmp_tbl += '</table>'
    
    resp = Response(tmp_tbl, status=200, mimetype='text/html')
    return resp


def write_authorized_keys(key):
    
    write_to_authorized_keys = True
    
    auth_file = os.path.join(remote_user_home, '.ssh','authorized_keys')
    if os.path.exists(auth_file):
        for l in open(auth_file):
            if l.strip() == key:
                print "pub key exists, skipping"
                write_to_authorized_keys = False
    else:
        if getpass.getuser() == 'root':
            uinfo = pwd.getpwnam(REMOTE_USER)
            ssh_dir = os.path.join(remote_user_home, '.ssh')
            
            if not os.path.exists(ssh_dir):
                os.mkdir(ssh_dir)
                os.chown(ssh_dir, uinfo.pw_uid, uinfo.pw_gid)
            
            open(auth_file,'w')
            
            os.chown(auth_file, uinfo.pw_uid, uinfo.pw_gid)

    if write_to_authorized_keys:
        F=open(auth_file,'a')
        F.write(key)
        F.write('\n')
        F.close()



@app.route('/hostname/<ip_addr>/<host_id>', methods=['GET'])
def get_host_name(ip_addr, host_id):

    resultDict={'host_name':None}
    status=404
    skey=request.headers.get('secret_key')
    print "skey", skey
    print "ip",ip_addr
    print "hid", host_id
    remote_id_rsa_pub = request.headers.get('id_rsa_pub')
    
    if skey == __SECRET_KEY__:
        
        write_authorized_keys(remote_id_rsa_pub)
        status=200

        r=Host.query.filter_by(ip_addr=ip_addr).first()

        id_rsa_pub = open(os.path.join(remote_user_home, '.ssh','id_rsa.pub')).read()
        
        resultDict['id_rsa_pub'] = id_rsa_pub.strip()
        resultDict['remote_user'] = REMOTE_USER
        
        if r:
            resultDict['host_name'] = r.host_name
            r.last_date=datetime.datetime.now()
            db.session.commit()
        else:
            r=Host.query.order_by(Host.id.desc()).first()
            if r:
                resultDict['host_name'] = 'H'+str(int(r.host_name[1:])+1).zfill(2)
            else:
                resultDict['host_name']='H01'
            
            new_host = Host(resultDict['host_name'], ip_addr, host_id, datetime.datetime.now())
            db.session.add(new_host)
            db.session.commit()
            

    resp = Response(json.dumps(resultDict), status=status, mimetype='application/json')
    return resp

def check_host_by_time():
    td = datetime.timedelta(days=30)
    while True:
        print "Checking host's date"
        for host in Host.query.all():
            print host.last_date + td, datetime.date.today()
            if host.last_date + td < datetime.date.today():
                print "deleting", host.host_id
                db.session.delete(host)
                db.session.commit()
            else:
                print "No need to delete",host.host_id 

        time.sleep(24*60*60)

def generate_pub_key():
    if not os.path.exists(os.path.join(remote_user_home, '.ssh','id_rsa.pub')):
        
        print "generating ssh key at", remote_user_home
        if getpass.getuser() == 'root':
            os.system("sudo -u %s ssh-keygen -f %s/.ssh/id_rsa -t rsa -N ''" % (REMOTE_USER, remote_user_home))
        else:
            os.system("ssh-keygen -f %s/.ssh/id_rsa -t rsa -N ''" % remote_user_home)

if __name__ == "__main__":
    
    t = Timer(0, check_host_by_time)
    t.start()
    generate_pub_key()
    #app.debug=True #!! WARNING: comment out this line in production !!
    app.run(host="0.0.0.0", port=PORT)
