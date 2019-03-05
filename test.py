import orm
import asyncio
from models import User

def test(loop):
    yield from orm.create_pool(loop=loop,user='wdji', password='123456',db='webapp')

    u = User(name='Test', email='test@example.com', passwd='1234567890', image='about:blank')
    yield from u.save()

loop = asyncio.get_event_loop()
loop.run_until_complete(test(loop))
loop.run_forever()

for x in test(loop):
    pass