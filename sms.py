#!/usr/bin/env python
# -*- coding: utf-8 -*-

from serial import Serial
from time import sleep
import sqlite3
from bottle import (Bottle, run, debug, template, static_file,
                    request, response, redirect)
import thread
import urllib
import json


class SMS:

    def __init__(self, port):
        try:
            self.serial = Serial(port, 9600)
            self.write('AT+CMGF=1\r')
            self.serial.read(self.serial.inWaiting())
            self.write('AT+CNMI=2,1\r')
            self.serial.read(self.serial.inWaiting())
        except:
            raise

    def send(self, number, message):
        try:
            self.write('AT+CSCS="GSM"\r')
            sleep(0.2)
            self.write('AT+CSMP=17,167,2,25\r')
            sleep(0.2)
            self.write('AT+CSCS="UCS2"\r')
            sleep(0.2)
            messages = self.UTF2Hex(message)
            for k in range((len(messages) - 1) // 280 + 1):
                self.write('AT+CMGS="%s"\r' % (self.UTF2Hex(number)), False)
                sleep(0.2)
                self.serial.write(messages[k * 280:k * 280 + 280])
                sleep(0.2)
                self.write(chr(0x1A))
                sleep(0.2)
            return True
        except:
            return False

    def wait(self):
        try:
            string = self.serial.readline(self.serial.inWaiting())
            result = {}
            if len(string) > 0:
                if string[:5] == '+CMTI':
                    seq = int(string.split(',')[1][:-1])
                    string = self.write('AT+CMGR=%d\r' % (seq))
                    result['seq'] = seq
                    result['number'] = self.Hex2UTF(string.split('","')[1])
                    sleep(0.2)
                    string = self.serial.readline()
                    result['content'] = self.Hex2UTF(string.split('\r')[0])
                    # print result['content']
                    string = self.write('AT+CMGD=%d\r' % (seq))
                    par = urllib.urlencode({
                        'phone': result['number'],
                        'content': result['content'].encode('utf-8')
                    })
                    f = urllib.urlopen(
                        "http://" + host + ":"
                        + str(port) + "/receive?" + par).read()
        except:
            return {"status": "error"}
        result["status"] = "success"
        return result

    def check(self):
        f = urllib.urlopen(
            "http://" + host + ":" + str(port) + "/unsent").read()
        row = json.loads(f)
        if row['status'] != 'success':
            return
        if not self.send(row['number'], row['content']):
            return
        f = urllib.urlopen(
            "http://" + host + ":" + str(port)
            + "/sent?id=" + str(row['id'])).read()

    def write(self, command, read=True):
        self.serial.write(command)
        string = self.serial.read(self.serial.inWaiting())
        if read:
            string += self.serial.readline()
            string += self.serial.readline()
        return string

    def UTF2Hex(self, s):
        res = ""
        if type(s) != type(u"123"):
            s = unicode(s, 'utf-8')
        for c in s:
            code = "%02X" % ord(c)
            if len(code) == 2:
                code = "00" + code
            res += code
        return res

    def Hex2UTF(self, hex_str):
        assert len(hex_str) % 4 == 0
        result = ""
        i = 0
        length = len(hex_str)
        while i < length:
            result += unichr(int(hex_str[i:i + 4], 16))
            i += 4
        return result


def smsThread():
    k = 0
    while True:
        k = k + 1
        sleep(1)
        print sms.wait()
        if k % 5 == 0:
            sms.check()

db = sqlite3.connect("db.sqlite3")
dao = db.cursor()
db.execute(
    'create table IF NOT EXISTS receive '
    + '(id integer primary key,'
    + 'number varchar(20),'
    + 'timestamp datetime default CURRENT_TIMESTAMP ,'
    + 'content varchar(240) )')
db.execute(
    'create table IF NOT EXISTS send '
    + '(id integer primary key,'
    + 'number varchar(20),'
    + 'timestamp datetime default CURRENT_TIMESTAMP,'
    + 'status integer default 0,'
    + 'content varchar(240) )')
try:
    sms = SMS('com6')
except:
    print 'COM Bind Failure!'
    exit()

app = Bottle()
app.Debug = True


@app.route('/')
def index():
    dao.execute(
        "select number,content,datetime(timestamp,'localtime') from send")
    sends = [{"phone": each[0], "content":each[1], "time":each[2]}
             for each in dao.fetchall()]
    dao.execute(
        "select number,content,datetime(timestamp,'localtime') from receive")
    recvs = [{"phone": each[0], "content":each[1], "time":each[2]}
             for each in dao.fetchall()]
    return {"status": 'success',
            'send': sends,
            'recvs': recvs}


@app.route('/send')
def send():
    my_dict = request.query.decode()
    phone = my_dict.phone
    content = my_dict.content
    dao.execute(
        'INSERT INTO send (number,content) values ("%s","%s")'
        % (phone, content))
    db.commit()
    return {"status": 'success', "phone": phone, "content": content}


@app.route('/sent')
def sent():
    my_dict = request.query.decode()
    msgId = my_dict.id
    dao.execute('UPDATE send set status = 1 WHERE id=%s' % (msgId))
    db.commit()
    return {"status": 'success'}


@app.route('/receive')
def receive():
    my_dict = request.query.decode()
    phone = my_dict.phone
    content = my_dict.content
    dao.execute(
        'INSERT INTO receive (number,content) values ("%s","%s")'
        % (phone, content))
    db.commit()
    return {"status": 'success', "phone": phone, "content": content}


@app.route('/unsent')
def unsent():
    my_dict = request.query.decode()
    msgId = my_dict.id
    dao.execute('select * from send WHERE status = 0')
    row = dao.fetchone()
    if row is None:
        return {"status": "empty"}
    return {"status": 'success',
            'id': row[0],
            "number": row[1],
            "content": row[4]}

host = 'localhost'
port = 8000

if __name__ == '__main__':
    thread.start_new_thread(smsThread, ())
    run(app, host=host, port=port)
