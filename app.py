from flask import Flask, render_template, request, redirect, url_for, flash
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from startup_setup import Base, Startup, Founder, User
#import for anti-forgery state token.
from flask import session as login_session
import random
import string

#import for Gconnect
from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError
import httplib2
import json
from flask import make_response
import requests

CLIENT_ID = json.loads(
    open('client_secrets.json', 'r').read())['web']['client_id']
APPLICATION_NAME = "Startup"

app = Flask(__name__)

engine = create_engine('sqlite:///startup.db')
Base.metadata.bind = engine

DBSession = sessionmaker(bind=engine)
session = DBSession()

# Create anti-forgery state token
@app.route('/login')
def showLogin():
    state = ''.join(random.choice(string.ascii_uppercase + string.digits)
                    for x in xrange(32))
    login_session['state'] = state
    # return "The current session state is %s" % login_session['state']
    return render_template('login.html', STATE=state)


@app.route('/gconnect', methods=['POST'])
def gconnect():
    # Validate state token
    if request.args.get('state') != login_session['state']:
        response = make_response(json.dumps('Invalid state parameter.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    # Obtain authorization code
    code = request.data

    try:
        # Upgrade the authorization code into a credentials object
        oauth_flow = flow_from_clientsecrets('client_secrets.json', scope='')
        oauth_flow.redirect_uri = 'postmessage'
        credentials = oauth_flow.step2_exchange(code)
    except FlowExchangeError:
        response = make_response(
            json.dumps('Failed to upgrade the authorization code.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Check that the access token is valid.
    access_token = credentials.access_token
    url = ('https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=%s'
           % access_token)
    h = httplib2.Http()
    result = json.loads(h.request(url, 'GET')[1])
    # If there was an error in the access token info, abort.
    if result.get('error') is not None:
        response = make_response(json.dumps(result.get('error')), 500)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is used for the intended user.
    gplus_id = credentials.id_token['sub']
    if result['user_id'] != gplus_id:
        response = make_response(
            json.dumps("Token's user ID doesn't match given user ID."), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is valid for this app.
    if result['issued_to'] != CLIENT_ID:
        response = make_response(
            json.dumps("Token's client ID does not match app's."), 401)
        print "Token's client ID does not match app's."
        response.headers['Content-Type'] = 'application/json'
        return response

    stored_access_token = login_session.get('access_token')
    stored_gplus_id = login_session.get('gplus_id')
    if stored_access_token is not None and gplus_id == stored_gplus_id:
        response = make_response(json.dumps('Current user is already connected.'),
                                 200)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Store the access token in the session for later use.
    login_session['access_token'] = credentials.access_token
    login_session['gplus_id'] = gplus_id

    # Get user info
    userinfo_url = "https://www.googleapis.com/oauth2/v1/userinfo"
    params = {'access_token': credentials.access_token, 'alt': 'json'}
    answer = requests.get(userinfo_url, params=params)

    data = answer.json()

    login_session['username'] = data['name']
    login_session['picture'] = data['picture']
    login_session['email'] = data['email']

    #see if user exists, if it doesn't make a new one
    user_id = getUserID(login_session['email'])
    if not user_id:
        user_id = createUser(login_session)
    login_session['user_id'] = user_id


    output = ''
    output += '<h1>Welcome, '
    output += login_session['username']
    output += '!</h1>'
    output += '<img src="'
    output += login_session['picture']
    output += ' " style = "width: 300px; height: 300px;border-radius: 150px;-webkit-border-radius: 150px;-moz-border-radius: 150px;"> '
    flash("you are now logged in as %s" % login_session['username'])
    print "done!"
    return output

    # DISCONNECT - Revoke a current user's token and reset their login_session

@app.route('/gdisconnect')
def gdisconnect():
    access_token = login_session.get('access_token')
    if access_token is None:
        print 'Access Token is None'
        response = make_response(json.dumps('Current user not connected.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    print 'In gdisconnect access token is %s', access_token
    print 'User name is: '
    print login_session['username']
    url = 'https://accounts.google.com/o/oauth2/revoke?token=%s' % login_session['access_token']
    h = httplib2.Http()
    result = h.request(url, 'GET')[0]
    print 'result is '
    print result
    if result['status'] == '200':
        del login_session['access_token']
        del login_session['gplus_id']
        del login_session['username']
        del login_session['email']
        del login_session['picture']
        response = make_response(json.dumps('Successfully disconnected.'), 200)
        response.headers['Content-Type'] = 'application/json'
        return response
    else:
        response = make_response(json.dumps('Failed to revoke token for given user.', 400))
        response.headers['Content-Type'] = 'application/json'
        return response


@app.route('/')
@app.route('/startup')
def showStartup():
    startups = session.query(Startup).all()
    if 'username' not in login_session:
        return  render_template('publicstartup.html', startups = startups)
    else:
        return  render_template('startups.html', startups = startups)

@app.route('/startup/new', methods=['GET', 'POST'])
def newStartup():
    if 'username' not in login_session:
        return redirect('/login')
    if request.method == 'POST':
        newStartup = Startup(name=request.form['name'])
        session.add(newStartup)
        session.commit()
        flash("new startup created!")
        return redirect(url_for('showStartup'))
    else:
        return  render_template('newStartup.html')

@app.route('/startup/<int:startup_id>/edit', methods=['GET', 'POST'])
def editStartup(startup_id):
    editedSartup = session.query(Startup).filter_by(id=startup_id).one()
    user = True
    if 'username' not in login_session:
        return redirect('/login')
    if editedSartup.user_id != login_session['user_id']:
        user = False
        return """<script>function myFunction(){
                      alert('You are not authorized to edit this restaurant.Please create your own restaurant in order to edit.');
                                      }
                  </script>
                      <body onload='myFunction()'>"""
    if request.method == 'POST':
        if request.form['name']:
            editedSartup.name = request.form['name']
        session.add(editedSartup)
        session.commit()
        return redirect(url_for('showStartup'))
    else:
        return  render_template('editStartup.html', startup = editedSartup)

@app.route('/startup/<int:startup_id>/delete',  methods=['GET', 'POST'])
def deleteStartup(startup_id):
    deletedstartup = session.query(Startup).filter_by(id=startup_id).one()
    if 'username' not in login_session:
        return redirect('/login')
    if deletedstartup.user_id != login_session['user_id']:
        return """<script>function myFunction(){
                      alert('You are not authorized to edit this restaurant.Please create your own restaurant in order to edit.');
                                      }
                  </script>
                      <body onload='myFunction()'>"""
    if request.method == 'POST':
        session.delete(deletedstartup)
        session.commit()
        return redirect(url_for('showStartup'))
    else:
        return  render_template('deleteStartup.html', startup = deletedstartup)

@app.route('/startup/<int:startup_id>/details')
def detailsStartup(startup_id):
    startup = session.query(Startup).filter_by(id=startup_id).one()
    founders = session.query(Founder).filter_by(startup_id=startup.id)
    if 'username' not in login_session:
        return  render_template('publicdetailsStartup.html', startup = startup , founders = founders)
    else:
        return  render_template('detailsStartup.html', startup = startup , founders = founders)

@app.route('/startup/<int:startup_id>/details/newFounder',  methods=['GET', 'POST'])
def newFounder(startup_id):
    startup = session.query(Startup).filter_by(id=startup_id).one()
    if 'username' not in login_session:
        return redirect('/login')
    if request.method == 'POST':
        newFounder = Founder(name=request.form['name'],bio=request.form['bio'],startup_id = startup.id)
        session.add(newFounder)
        session.commit()
        flash("new founder created!")
        return redirect(url_for('detailsStartup',startup_id = startup_id))

    else:
        return  render_template('newFounder.html', startup = startup)

@app.route('/startup/<int:startup_id>/details/editeFounder/<int:founder_id>',  methods=['GET', 'POST'])
def editFounder(startup_id, founder_id):
    editFounder = session.query(Founder).filter_by(id=founder_id).one()
    if 'username' not in login_session:
        return redirect('/login')
    if editFounder.user_id != login_session['user_id']:
        return """<script>function myFunction(){
                      alert('You are not authorized to edit this restaurant.Please create your own restaurant in order to edit.');
                                      }
                  </script>
                      <body onload='myFunction()'>"""
    if request.method == 'POST':
            if request.form['name']:
                editedFounder.name = request.form['name']
            if request.form['bio']:
                editedFounder.bio = request.form['bio']
            session.add(editedFounder)
            session.commit()
            return redirect(url_for('detailsStartup',   startup_id = startup_id))
    else:
            return  render_template('editFounder.html', startup_id = startup_id, founder = editedFounder)

@app.route('/startup/<int:startup_id>/details/deleteFounder/<int:founder_id>',  methods=['GET', 'POST'])
def deleteFounder(startup_id, founder_id):
    deletedFounder = session.query(Founder).filter_by(id=founder_id).one()
    if 'username' not in login_session:
        return redirect('/login')
    if deletedFounder.user_id != login_session['user_id']:
        return """<script>function myFunction(){
                      alert('You are not authorized to edit this restaurant.Please create your own restaurant in order to edit.');
                                      }
                  </script>
                      <body onload='myFunction()'>"""
    if request.method == 'POST':
            session.delete(deletedFounder)
            session.commit()
            return redirect(url_for('detailsStartup',   startup_id = startup_id))
    else:
            return  render_template('deleteFounder.html', startup_id = startup_id, founder = deletedFounder)
# User Helper Functions
def createUser(login_session):
    newUser = User(name=login_session['username'], email=login_session[
                   'email'], picture=login_session['picture'])
    session.add(newUser)
    session.commit()
    user = session.query(User).filter_by(email=login_session['email']).one()
    return user.id


def getUserInfo(user_id):
    user = session.query(User).filter_by(id=user_id).one()
    return user


def getUserID(email):
    try:
        user = session.query(User).filter_by(email=email).one()
        return user.id
    except:
        return None


if __name__ == '__main__':
    app.secret_key = 'super_secret_key'
    app.debug = True
    app.run(host='0.0.0.0', port=5000)
