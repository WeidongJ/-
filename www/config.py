#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import config_default

class Dict(dict):

    def __init__(self, names=(), values=(), **kw):
        super(Dict, self).__init__(**kw)
        for k, v in zip(names, values): # zip将可迭代入参打包成元组，python3返回一个对象
            self[k] = v

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"'Dict' object has no attrbuite '%s'" % key)

    def __setattr__(self, key, value):
        self[key] = value

def merge(defaults,override): # 递归函数复写config
    r = {}
    for k, v in defaults.items():
        if k in override:
            if isinstance(v, dict): 
                r[k] = merge(v,override[k])
            else:
                r[k] = override[k]
        else:
            r[k] = v
    return r

def toDict(d):
    D = Dict()
    for k, v in d.items():
        D[k] = toDict(v) if isinstance(v, dict) else v
    return D

configs = config_default.configs

try:
    import config_override
    configs = merge(configs, config_override.configs)
except ImportError:
    pass

configs = toDict(configs)
print(configs.session.secret)
    
