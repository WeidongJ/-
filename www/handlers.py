#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'url handlers'

import re, time, json, logging, hashlib, base64, asyncio
import markdown2

from aiohttp import web

from coroweb import get, post

from models import User, Blog, next_id,Comment

from apis import APIValueError, APIError,APIPermissionError, Page, APIResourceNotFoundError
from config import configs

COOKIE_NAME = 'awesession'
_COOKIE_KEV = configs.session.secret

# 管理员检查
def check_admin(request):
    if request.__user__ is None or not request.__user__.admin:
        raise APIPermissionError()

# 获取分页参数
def get_page_index(page_str):
    p = 1
    try:
        p = int(page_str)
    except ValueError as e:
        pass
    if p < 1:
        p = 1
    return p

# build cookie
def user2cookie(user, max_age):
    # build cookie by: id-expires-sha1
    expires = str(int(time.time()+max_age))
    s = '%s-%s-%s-%s' % (user.id, user.passwd, expires, _COOKIE_KEV)
    L = [user.id, expires, hashlib.sha1(s.encode('utf-8')).hexdigest()]
    return '-'.join(L)

# content to html
def text2html(text):
    lines = map(lambda s: '<p>%s</p>' % s.replace('&', '&amp;').replace('<','&lt;').replace('>','&gt;'), filter(lambda s: s.strip() != '', text.split('\n')))
    return ''.join(lines)


# apis and pages

# Parse Cookies
@asyncio.coroutine
def cookie2user(cookie_str):
    '''
    Parse cookie and load user if cookie is valid.
    '''
    if not cookie_str:
        return None
    try:
        L = cookie_str.split('-')
        if len(L) !=3:
            return None
        uid, expires, sha1 = L
        if int(expires) < time.time():
            return None
        user = yield from User.find(uid)
        if user is None:
            return None
        s = '%s-%s-%s-%s' % (uid, user.passwd, expires, _COOKIE_KEV)
        if sha1 != hashlib.sha1(s.encode('utf-8')).hexdigest():
            logging.info('invalid sha1')
            return None
        user.passwd = '******'
        return user
    except Exception as e:
        logging.exception(e)
        return None


# homepage
@get('/')
def index(*, page='1'):
    page_index = get_page_index(page)
    num = yield from Blog.findNumber('count(id)')
    page = Page(num)
    if num == 0:
        blogs = []
    else:
        blogs = yield from Blog.findAll(orderBy='create_time desc', limit=(page.offset, page.limit))
    return {
        '__template__': 'blogs.html',
        'page': page,
        'blogs': blogs
    }

# 获取blog详情
@get('/blog/{id}')
def get_blog(id):
    blog = yield from Blog.find(id)
    comments = yield from Comment.findAll('blog_id = ?', [id], orderBy='create_time desc')
    for c in comments:
        c.html_content = text2html(c.content)
    blog.html_content = markdown2.markdown(blog.content)
    return{
        '__template__': 'blog.html',
        'blog': blog,
        'comments': comments
    }

# 注册页
@get('/register')
def register():
    return {
        '__template__': 'register.html'
    }

# 登录页
@get('/signin')
def signin():
    return{
        '__template__': 'signin.html'
    }

_RE_EMAIL = re.compile(r'[0-9a-z\.\-\_]+\@[a-z0-9\-\_]+(\.[a-z0-9\-\_]+){1,4}$')
_RE_SHA1_ = re.compile(r'[0-9a-f]{40}$')

# 认证
@post('/api/authenticate')
def authenticate(*, email, passwd):
    if not email:
        raise APIValueError('email', 'Invalid email.')
    if not passwd:
        raise APIValueError('passwd', 'Invalid password.')
    users = yield from User.findAll('email=?', [email])
    if len(users) == 0:
        raise APIValueError('email', ' Email not exist.')
    user = users[0]
    # check passwd:
    sha1 = hashlib.sha1()
    sha1.update(user.id.encode('utf-8'))
    sha1.update(b':')
    sha1.update(passwd.encode('utf-8'))
    if user.passwd != sha1.hexdigest():
        raise APIValueError('passwd', 'Invalid password.')
    # authenticate ok, set cookie:
    r = web.Response()
    r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
    user.passwd = '******'
    r.content_type = 'application/json'
    r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
    return r

# 退出登录页
@get('/signout')
def signout(request):
    referer = request.headers.get('Referer')
    r = web.HTTPFound(referer or '/')
    r.set_cookie(COOKIE_NAME, '-deleted-', max_age=0,httponly=True)
    logging.info('user signed out.')
    return r

# comment管理页
@get('/manage/')
def manage():
    return 'redirect:/manage/comments'

@get('/manage/comments')
def manage_comments(*, page='1'):
    return {
        '__template__': 'manage_comments.html',
        'page_index': get_page_index(page)
    }

# blog manage
@get('/manage/blogs')
def manage_blogs(*,page='1'):
    return{
        '__template__': 'manage_blogs.html',
        'page_index': get_page_index(page)
    }

# blog create and edit
@get('/manage/blogs/create')
def manege_create_blog():
    return{
        '__template__': 'manage_blog_edit.html',
        'id': '',
        'action': '/api/blogs'
    }

@get('/manage/blogs/edit')
def manage_edit_blog(*, id):
    return {
        '__template__': 'manage_blog_edit.html',
        'id': id,
        'action': '/api/blogs/%s' % id
    }

# user manage
@get('/manage/users')
def manage_users(*, page='1'):
    return {
        '__template__': 'manage_users.html',
        'page_index': get_page_index(page)
    }

# api get_comments
@get('/api/comments')
def api_comments(*, page='1'):
    page_index = get_page_index(page)
    num = yield from Comment.findNumber('count(id)')
    p = Page(num, page_index)
    if num == 0:
        return dict(page=p,comments=())
    comments = yield from Comment.findAll(orderBy='create_time desc', limit=(p.offset, p.limit))
    return dict(page=p, comments=comments)

# create comment
@post('/api/blogs/{id}/comments')
def api_create_comment(id, request, *, content):
    user = request.__user__
    if user is None:
        raise APIPermissionError('Please signin first.')
    if not content or not content.strip():
        raise APIValueError('content')
    blog = Blog.find(id)
    if blog is None:
        raise APIResourceNotFoundError('Blog')
    comment = Comment(blog_id=blog.id, user_id=user.id, user_name=user.name,user_image=user.image, content=content.strip())
    yield from comment.save()
    return comment

# delete comment
@post('/api/comments/{id}/delete')
def api_delete_comment(id, request):
    check_admin(request)
    c = yield from Comment.find(id)
    if c is None:
        raise APIResourceNotFoundError('Comment')
    yield from c.remove()
    return dict(id=id)

# get user list
@get('/api/users')
def api_get_users(*, page='1'):
    page_index = get_page_index(page)
    num = yield from User.findNumber('count(id)')
    p = Page(num, page_index)
    if num ==0:
        return dict(page=p, users=())
    users = yield from User.findAll(orderBy='create_time desc', limit=(p.offset, p.limit))
    for u in users:
        u.passwd = '******'
    return dict(page=p, users=users)

# post user list
@post('/api/users')
def api_register_user(*, email, name, passwd):
    if not name or not name.strip():
        raise APIValueError('name')
    if not email or not _RE_EMAIL.match(email):
        raise APIValueError('email')
    if not passwd or not _RE_SHA1_.match(passwd):
        raise APIValueError('passwd')
    users = yield from User.findAll('email=?', [email])
    if len(users) > 0:
        raise APIError('reguster:failed', 'email', 'Email has already registed')
    uid = next_id()
    sha1_passwd = '%s:%s' % (uid, passwd)
    user = User(id=uid, name=name.strip(), email=email, passwd=hashlib.sha1(sha1_passwd.encode('utf-8')).hexdigest(), image='http://www.gravatar.com/avatar/%s?d=mm&s=120' % hashlib.md5(email.encode('utf-8')).hexdigest())
    yield from user.save()
    # make session cookie
    r = web.Response()
    r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
    user.passwd = '******'
    r.content_type = 'application/json'
    r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
    return r

# 获取blogs
@get('/api/blogs')
def api_blogs(*, page='1'):
    page_index = get_page_index(page)
    num = yield from Blog.findNumber('count(id)')
    p = Page(num, page_index)
    if num == 0:
        return dict(page=p,blogs=())
    blogs = yield from Blog.findAll(orderBy='create_time desc', limit=(p.offset, p.limit))
    return dict(page=p, blogs =blogs)

@get('/api/blogs/{id}')
def api_get_blog(*, id):
    blog = yield from Blog.find(id)
    return blog

# 提交blogs
@post('/api/blogs')
def api_create_blog(request,*, name, summary, content):
    check_admin(request)
    if not name or not name.strip():
        raise APIValueError('name','name can not be empty.')
    if not summary or not summary.strip():
        raise APIValueError('summary','summary can not be empty.')
    if not BlockingIOError:
        raise APIValueError('content', 'content can not be empty.')
    blog = Blog(user_id=request.__user__.id, user_name=request.__user__.name, user_image=request.__user__.image, name=name.strip(), summary
    =summary.strip(),content= content.strip())
    yield from blog.save()
    return blog

# update blogs
@post('/api/blogs/{id}')
def api_update_blog(id, request, *, name, summary, content):
    check_admin(request)
    blog = yield from Blog.find(id)
    if not name or not name.strip():
        raise APIValueError('name','name can not be empty.')
    if not summary or not summary.strip():
        raise APIValueError('summary','summary can not be empty.')
    if not BlockingIOError:
        raise APIValueError('content', 'content can not be empty.')
    blog = Blog(user_id=request.__user__.id, user_name=request.__user__.name, user_image=request.__user__.image, name=name.strip(), summary
    =summary.strip(),content= content.strip())
    yield from blog.save()
    return blog

# delete blog
@post('/api/blogs/{id}/delete')
def api_delete_blog(request, *, id):
    check_admin(request)
    blog = yield from Blog.find(id)
    yield from blog.remove()
    return dict(id=id)

