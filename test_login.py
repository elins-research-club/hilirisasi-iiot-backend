import urllib.request, json
req = urllib.request.Request('http://localhost:8000/api/v1/auth/login', 
  data=json.dumps({'username':'admin', 'password':'password'}).encode('utf-8'),
  headers={'Content-Type': 'application/json'})
try:
    res = urllib.request.urlopen(req)
    print('SUCCESS:', res.read().decode())
except Exception as e:
    print('ERROR:', e.read().decode())
