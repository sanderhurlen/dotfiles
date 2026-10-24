# Another bin as a module (fleet reads wr's PRs, wi's triage, …). Loaded once per
# process, so every bin that loads wf shares its tracker and cache.

import importlib.machinery
import importlib.util
import os
import sys

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "bin")


def load(name):
    if name in sys.modules:
        return sys.modules[name]
    loader = importlib.machinery.SourceFileLoader(name, os.path.join(BIN, name))
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader))
    sys.modules[name] = mod
    try:
        loader.exec_module(mod)
    except BaseException:
        del sys.modules[name]
        raise
    return mod
