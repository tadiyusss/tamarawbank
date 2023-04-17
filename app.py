from flask import Flask, render_template, request, redirect, session
from pysondb import getDb
from datetime import datetime
import hashlib
import string
import random
import qrcode
import os
import sys
import json


def random_string(length):
    return ''.join(random.choice(string.ascii_letters) for i in range(length))

if os.path.exists('config.json') != True:
    config = {
        'debug': False,
        'host': '0.0.0.0',
        'port': 5000,
        'hash_key': random_string(32)
    }
    file = open('config.json', 'w')
    file.write(json.dumps(config))
    file.close()
else:
    file = open('config.json', 'r')
    config = json.loads(file.read())
    file.close()

if '--debug' in sys.argv:
    config['debug'] = True

if '--reset' in sys.argv:
    if 'transactions.json' in os.listdir('.'):
        os.remove('transactions.json')
    if 'users.json' in os.listdir('.'):
        os.remove('users.json')
    if 'log.txt' in os.listdir('.'):
        os.remove('log.txt')
    if 'config.json' in os.listdir('.'):
        os.remove('config.json')
    for file in os.listdir('static/qr'):
        os.remove('static/qr/' + file)
    exit()

def log(message):
    file = open('log.txt', 'a')
    file.write(f"[{datetime.now()}] {message}\n")
    file.close()

def hash_password(password):
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), config['hash_key'].encode(), 10000)
    return digest.hex()

users_db = getDb('users.json')
transactionHistory = getDb('transactions.json')
app = Flask(__name__)
app.secret_key = random_string(32)

@app.route('/dashboard/edit_profile', methods=['GET', 'POST'])
def dashboard_editProfile():
    if 'student_number' in session:
        if request.method == 'POST':
            data = {
                'fname': request.form['fname'],
                'lname': request.form['lname'],
                'mobile_number': request.form['mobile_number'],
                'address': request.form['address']
            }
            users_db.update({"student_number": session['student_number']}, data)
            for key, value in data.items():
                session[key] = value
            log(f"User {session['student_number']} updated their profile")
            return redirect('/dashboard')
        else:
            return render_template('edit_profile.html')
    else:
        return redirect('/')
    
@app.route('/dashboard')
def dashboard():
    if 'student_number' in session:
        if os.path.exists('static/qr/' + session['student_number'] + '.png') != True:
            img = qrcode.make(session['student_number'])
            img.save('static/qr/' + session['student_number'] + '.png')
        return render_template('dashboard.html')
    else:
        print('Not logged in')
        return redirect('/')

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == "POST":
        data = users_db.getByQuery({'student_number': request.form['student_number']})
        if len(data) > 0:
            if data[0]['password'] == hash_password(request.form['password']):
                # Login successful
                session['student_number'] = data[0]['student_number']
                return redirect('/dashboard')
            else:
                # Incorrect password
                return render_template('login.html', error='Invalid username or password')
        else:
            # Invalid username
            return render_template('login.html', error='Invalid username or password')
    else:
        if 'student_number' in session:
            # If user is already logged in
            return redirect('/dashboard')
        # GET request
        return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        fname = request.form['fname']
        lname = request.form['lname']
        mobile_number = request.form['mobile_number']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        student_email = request.form['student_email']
        student_number = request.form['student_number']
        address = request.form['address']
        data = {
            'fname': fname,
            'lname': lname,
            'mobile_number': mobile_number,
            'password': hash_password(password),
            'student_email': student_email,
            'address': address,
            'student_number': student_number,
            'pin': False,
            'balance': 0.00
        }
        # Check if all fields are filled
        for key, value in data.items():
            if value == '':
                return render_template('registration.html', error='Please fill in all fields')
            
        # Check if student number already exists
        if len(users_db.getByQuery({'student_number': student_number})) > 0:
            return render_template('registration.html', error='Student number already exists')

        # Check if passwords match
        elif password != confirm_password:
            return render_template('registration.html', error='Passwords do not match')
        
        # Check if student email already exists
        elif len(users_db.getByQuery({'student_email': student_email})) > 0:
            return render_template('registration.html', error='Student email already exists')
        
        # Save data to database
        else:
            log(f"User {student_number} registered")
            users_db.add(data)
            return render_template('login.html', success='Registration successful please login to continue')
    else:
        return render_template('registration.html')

@app.route('/api/user_data', methods=['POST'])
def api_getBalance():
    if 'student_number' in session:
        data = users_db.getByQuery({'student_number': session['student_number']})[0]
        data.pop('password')
        data.pop('student_email')
        data.pop('id')
        log(f"User {session['student_number']} requested their data")
        return {'status': 'success', 'data': data}
    else:
        return {'status': 'error', 'message': 'Not logged in'}

@app.route('/api/transaction_history', methods=['POST'])
def api_getTransactionHistory():
    if 'student_number' in session:
        if "identifier" in request.form:
            identifier = request.form['identifier']
            transactionHistory.updateByQuery({'identifier': identifier}, {'read': 1})
        sent = transactionHistory.getByQuery({'sender': session['student_number']})
        receiver = transactionHistory.getByQuery({'receiver': session['student_number']})
        sent.extend(receiver)
        sent.sort(key=lambda x: x['date'], reverse=True)
        log(f"User {session['student_number']} requested their transaction history")
        return {'status': 'success', 'data': sent}
    else:
        return {'status': 'error', 'message': 'Not logged in'}

@app.route('/api/send', methods=['POST'])
def dashboard_send():
    if 'student_number' in session:
        if request.method == 'POST':
            senders_data = users_db.getByQuery({'student_number': session['student_number']})[0]
            data = {
                'student_number': request.form['recipient'],
                'amount': request.form['amount'],
                'message': request.form['message'],
                'password': request.form['password']
            }
            # Check if all fields are filled
            for key, value in data.items():
                if key == 'message':
                    continue
                elif value == '':
                    return {'status': 'error','message': 'Please fill in all fields'}
            
            # Check if recipient exists
            if len(users_db.getByQuery({'student_number': data['student_number']})) == 0:      
                return {'status': 'error','message': 'Recipient does not exist'}
            
            # Check if password is correct
            elif hash_password(data['password']) != users_db.getByQuery({'student_number': session['student_number']})[0]['password']:
                return {'status': 'error','message': 'Incorrect password'}
            
            # Check if amount is valid
            elif float(data['amount']) <= 0:
                return {'status': 'error','message': 'Invalid amount'}
            
            # Check if user has enough balance
            elif float(data['amount']) > float(senders_data['balance']):
                return {'status': 'error','message': 'Insufficient balance'}
            
            # Check if user is sending to himself
            elif data['student_number'] == session['student_number']:
                return {'status': 'error','message': 'You cannot send to yourself'}
            
            # Send money
            else:
                # Update sender's balance
                users_db.updateById(senders_data['id'], {'balance': float(senders_data['balance']) - float(data['amount'])})
                senders_data['balance'] = float(senders_data['balance']) - float(data['amount'])
                # Update recipient's balance
                recipient = users_db.getByQuery({'student_number': data['student_number']})
                users_db.updateById(recipient[0]['id'], {'balance': float(recipient[0]['balance']) + float(data['amount'])})
                # Record transaction
                
                data = {
                    'sender': session['student_number'],
                    'receiver': data['student_number'],
                    'amount': data['amount'],
                    'message': data['message'],
                    'date': datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
                    'read': 0,
                    'status': 'success',
                    'identifier': random_string(24)
                }
                transactionHistory.add(data)
                log(f"User {session['student_number']} sent {data['amount']} to {data['receiver']}")
                return {'status': 'success','message': 'Money sent successfully'}
            
    else:
        return redirect('/')

@app.route("/api/validatePin", methods=['POST'])
def api_validatePin():
    if 'student_number' in session:
        if request.method == 'POST':
            data = {
                'pin': request.form['pin'],
            }
            return data
    else:
        return redirect('/')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

app.run(debug=config['debug'], host=config['host'], port=config['port'], ssl_context='adhoc')