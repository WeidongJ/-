#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'url handlers'

import re, time, json, logging, hashlib, base64, asyncio

from aiohttp import web

from coroweb import get, post

from models import User, Blog, next_id

from apis import APIValueError, APIError

@get('/')
@asyncio.coroutine
def index(request):
    summary = 'Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.'
    blogs = [
        Blog(id='1', name='Test Blog', summary=summary, create_time=time.time()-120),
        Blog(id='2', name='Something New', summary=summary, create_time=time.time()-3600),
        Blog(id='3', name='Learn Swift', summary=summary, create_time=time.time()-7200)
    ]
    return {
        '__template__': 'blogs.html',
        'blogs': blogs
    }

@get('/api/users')
@asyncio.coroutine
def api_get_users(*, page='1'): # 命名关键字参数
    users = yield from User.findAll(orderBy='create_time')
    for u in users:
        u.passwd = '******'
    return dict(users=users)

_RE_EMAIL = re.compile(r'[0-9a-z\.\-\_]+\@[a-z0-9\-\_]+(\.[a-z0-9\-\_]+){1,4}$')
_RE_SHA1_ = re.compile(r'[0-9a-f]{40}$')

@post('/api/register')
@asyncio.coroutine
def api_register_user(*, email, name, passwd):
    if not name or not name.strip():
        raise APIValueError('name')
    if not email or not _RE_EMAIL.match(email):
        raise APIValueError('email')
    if not passwd or not _RE_SHA1_.match(passwd):
        raise APIValueError('passwd')
    users = yield from User.findAll('email=', [email])
    if len(users) > 0:
        raise APIError('reguster:failed', 'email', 'Email has already registed')
    uid = next_id()
    sha1_passwd = '%s:%s' % (uid, email)
    user = User(id=uid, name=name, passwd=hashlib.sha1(sha1_passwd.encode('utf-8')).hexdigest(), img='http://\
    www.gravatar.com/avatar/%s?d=mm&s=120' % hashlib.md5(email.encode('utf-8')).hexdigest())
    yield from user.save()
    # make session cookie
    r = web.Response()
    r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
    user.passwd = '******'
    r.content_type = 'application/json'
    r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
    return r


