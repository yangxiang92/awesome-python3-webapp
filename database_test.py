import orm
import asyncio
import pdb
import time

from model import User, Blog, Comment;

@asyncio.coroutine
def test(loop):
    yield from orm.create_pool(loop, user='www-data', password = 'user-data', database = 'awesome');

    u = User(name = 'Test', email='test@example.com', passwd = '1234567890', image = 'about:blank');

    yield from u.save();

if __name__ == '__main__':
    loop = asyncio.get_event_loop();
    loop.run_until_complete(test(loop));
    __pool = orm.__pool;
    __pool.close();
    loop.run_until_complete(__pool.wait_closed());
    loop.close();
