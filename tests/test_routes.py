import urllib.request
try:
    res = urllib.request.urlopen('http://localhost:8000/docs')
    print('SUCCESS:', res.getcode())
except Exception as e:
    print('ERROR:', e.getcode())
