import asyncio
import functools
import inspect

import logging
logging.basicConfig(level = logging.INFO);

def get(path):
    '''
    Define decorator @get('/path');
    '''
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kw):
            return func(*args, **kw);
        wrapper.__method__ = 'GET';
        wrapper.__route__ = path;
        return wrapper;
    return decorator;

def post(path):
    '''
    Define decorator @post('/path');
    '''
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kw):
            return func(*args, **kw);
        wrapper.__method__ = 'POST';
        wrapper.__route__ = path;
        return wrapper;
    return decorator;


#==================================================================
# 初始化请求处理类函数
# ---------------------------- 使用inspect模块中的signature方法来获取函数的参数，实现一些复用功能--
# 关于inspect.Parameter 的  kind 类型有5种：
# POSITIONAL_ONLY		只能是位置参数
# POSITIONAL_OR_KEYWORD	可以是位置参数也可以是关键字参数
# VAR_POSITIONAL			相当于是 *args
# KEYWORD_ONLY			关键字参数且提供了key，相当于是 *,key
# VAR_KEYWORD			相当于是 **kw


def get_required_kw_args(fn):

    # 如果url处理函数需要传入关键字参数，且默认是空得话，获取这个key
    args = []
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        # param.default == inspect.Parameter.empty这一句表示参数的默认值要为空
        if param.kind == inspect.Parameter.KEYWORD_ONLY and param.default == inspect.Parameter.empty:
            args.append(name)
    return tuple(args)


def get_named_kw_args(fn):

    # 如果url处理函数需要传入关键字参数，获取这个key
    args = []
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY:
            args.append(name)
    return tuple(args)


def has_named_kw_args(fn):  # 判断是否有指定命名关键字参数
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY:
            return True


def has_var_kw_arg(fn):  # 判断是否有关键字参数，VAR_KEYWORD对应**kw
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            return True


# 判断是否存在一个参数叫做request，并且该参数要在其他普通的位置参数之后，即属于*kw或者**kw或者*或者*args之后的参数
def has_request_arg(fn):
    sig = inspect.signature(fn)
    params = sig.parameters
    found = False
    for name, param in params.items():
        if name == 'request':
            found = True
            continue
        # 只能是位置参数POSITIONAL_ONLY
        if found and (param.kind != inspect.Parameter.VAR_POSITIONAL and param.kind != inspect.Parameter.KEYWORD_ONLY and param.kind != inspect.Parameter.VAR_KEYWORD):
            raise ValueError('request parameter must be the last named parameter in function: %s%s' % (
                fn.__name__, str(sig)))
    return found

# RequestHandler目的就是从URL函数中分析其需要接收的参数，从request中获取必要的参数，
# 调用URL函数，然后把结果转换为web.Response对象，这样，就完全符合aiohttp框架的要求：

class RequestHandler(object):

    def __init__(self, app, fn):
        self._app = app
        self._func = fn
        self._has_request_arg = has_request_arg(fn)
        self._has_var_kw_arg = has_var_kw_arg(fn)
        self._has_named_kw_args = has_named_kw_args(fn)
        self._named_kw_args = get_named_kw_args(fn)
        self._required_kw_args = get_required_kw_args(fn)

    # __call__方法的代码逻辑:
    # 1.定义kw对象，用于保存参数
    # 2.判断request对象是否存在参数，如果存在则根据是POST还是GET方法将参数内容保存到kw
    # 3.如果kw为空(说明request没有传递参数)，则将match_info列表里面的资源映射表赋值给kw；如果不为空则把命名关键字参数的内容给kw
    # 4.完善_has_request_arg和_required_kw_args属性
    @asyncio.coroutine
    def __call__(self, request):
        kw = None
        # 确保有参数
        if self._has_var_kw_arg or self._has_named_kw_args or self._required_kw_args:

            # ------阶段1：POST/GET方法下正确解析request的参数，包括位置参数和关键字参数----
            #
            # POST提交请求的类型(通过content_type可以指定)可以参考我的博客：http://kaimingwan.com/post/python/postchang-jian-qing-qiu-fang-shi-qian-xi
            if request.method == 'POST':
                # 判断是否村存在Content-Type（媒体格式类型），一般Content-Type包含的值：
                # text/html;charset:utf-8;
                if not request.content_type:
                    return web.HTTPBadRequest('Missing Content-Type.')
                ct = request.content_type.lower()
                if ct.startswith('application/json'):
                    params = yield from request.json()  # 如果请求json数据格式
                    # 是否参数是dict格式，不是的话提示JSON BODY出错
                    if not isinstance(params, dict):
                        return web.HTTPBadRequest('JSON body must be object.')
                    kw = params  # 正确的话把request的参数信息给kw
                # POST提交请求的类型
                elif ct.startswith('application/x-www-form-urlencoded') or ct.startswith('multipart/form-data'):
                    params = yield from request.post()  # 调用post方法，注意此处已经使用了装饰器
                    kw = dict(**params)
                else:
                    return web.HTTPBadRequest('Unsupported Content-Type: %s' % request.content_type)
            if request.method == 'GET':  # get方法比较简单，直接后面跟了string来请求服务器上的资源
                qs = request.query_string
                if qs:
                    kw = dict()
                    # 该方法解析url中?后面的键值对内容保存到kw
                    for k, v in parse.parse_qs(qs, True).items():
                        kw[k] = v[0]
        if kw is None:  # 参数为空说明没有从Request对象中获取到必要参数
            # Resource may have variable path also. For instance, a resource
            # with the path '/a/{name}/c' would match all incoming requests
            # with paths such as '/a/b/c', '/a/1/c', and '/a/etc/c'.

            # A variable part is specified in the form {identifier}, where the
            # identifier can be used later in a request handler to access the
            # matched value for that part. This is done by looking up the
            # identifier in the Request.match_info mapping:
            kw = dict(**request.match_info)
            # 此时kw指向match_info属性，一个变量标识符的名字的dict列表。Request中获取的命名关键字参数必须要在这个dict当中
        # kw不为空时，还要判断下是可变参数还是命名关键字参数，如果是命名关键字参数，则需要remove all unamed kw，这是为啥？
        else:
            # 如果从Request对象中获取到参数了
            # 当没有可变参数，有命名关键字参数时候，kw指向命名关键字参数的内容
            if not self._has_var_kw_arg and self._named_kw_args:
                # remove all unamed kw: 删除所有没有命名的关键字参数
                copy = dict()
                for name in self._named_kw_args:
                    if name in kw:
                        copy[name] = kw[name]
                kw = copy
            # check named arg: 检查命名关键字参数的名字是否和match_info中的重复
            for k, v in request.match_info.items():
                if k in kw:
                    logging.warning(
                        'Duplicate arg name in named arg and kw args: %s' % k)  # 命名参数和关键字参数有名字重复
                kw[k] = v
        # 如果有request这个参数，则把request对象加入kw['request']
        if self._has_request_arg:
            kw['request'] = request
        # check required kw: 检查是否有必要关键字参数
        if self._required_kw_args:
            for name in self._required_kw_args:
                if name not in kw:
                    return web.HTTPBadRequest('Missing argument: %s' % name)
        logging.info('call with args: %s' % str(kw))
        try:
            r = yield from self._func(**kw)
            return r
        except APIError as e:
            return dict(error=e.error, data=e.data, message=e.message)

def add_route(app, fn):
    method = getattr(fn, '__method__', None);
    path = getattr(fn, '__route__', None);
    if path is None or method is None:
        raise ValueError('@get or @post not defined in %s' % (str(fn)));
    if not asyncio.iscoroutinefunction(fn) and not inspect.isgeneratorfunction(fn):
        fn = asyncio.coroutine(fn);
    logging.info('add route %s %s ==> %s(%s)' % (method, path, fn.__name__, ','.join(inspect.signature(fn).parameters.keys())));
    app.router.add_route(method, path, RequestHandler(app, fn));

def add_routes(app, module_name):
    n = module_name.rfind('.');
    if n == (-1):
        mod = __import__(module_name, globals(), locals());
    else:
        #name = module_name[n+1:];
        #mod = getattr(__import__(module_name[:n], globals(), locals(), [name]), name);
        mod = __import__(module_name[:n], globals(), locals());
    for attr in dir(mod):
        if attr.startswith('_'):
            continue;
        fn = getattr(mod, attr);
        if callable(fn):
            method = getattr(fn, '__method__', None);
            path = getattr(fn, '__route__', None);
            if method and path:
                add_route(app, fn);


