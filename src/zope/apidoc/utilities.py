##############################################################################
#
# Copyright (c) 2004 Zope Foundation and Contributors.
# All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
#
##############################################################################
"""Utilties to make the life of Documentation Modules easier.
"""
__docformat__ = 'restructuredtext'
import inspect
import re
import sys
import types
from os.path import dirname

import zope.i18nmessageid
from zope.apidoc._compat import PY3
from zope.apidoc._compat import unicode
from zope.apidoc.classregistry import IGNORE_MODULES
from zope.apidoc.classregistry import safe_import
from zope.component import createObject
from zope.component import getMultiAdapter
from zope.interface import implementedBy
from zope.publisher.browser import TestRequest
from zope.security.checker import Global
from zope.security.checker import getCheckerForInstancesOf
from zope.security.interfaces import INameBasedChecker
from zope.security.proxy import isinstance
from zope.security.proxy import removeSecurityProxy


_ = zope.i18nmessageid.MessageFactory("zope")

_remove_html_overhead = re.compile(
    r'(?sm)^<html.*<body.*?>\n(.*)</body>\n</html>\n')

space_re = re.compile(r'\n^( *)\S', re.M)

_marker = object()

BASEDIR = dirname(dirname(dirname(dirname(zope.apidoc.__file__))))


def relativizePath(path):
    return path.replace(BASEDIR, 'Zope3')


def truncateSysPath(path):
    """Remove the system path prefix from the path."""
    for syspath in sys.path:
        if path.startswith(syspath):
            return path.replace(syspath, '')[1:]
    return path


def getPythonPath(obj):
    """Return the path of the object in standard Python notation.

    This method should try very hard to return a string, even if it is not a
    valid Python path.
    """
    if obj is None:
        return None

    # Even for methods `im_class` and `__module__` is not allowed to be
    # accessed (which is probably not a bad idea). So, we remove the security
    # proxies for this check.
    naked = removeSecurityProxy(obj)
    name = naked.__name__
    if hasattr(naked, "im_class"):
        naked = naked.im_class
        name = naked.__name__
    # Py3 version:
    if PY3 and isinstance(naked, types.FunctionType):
        name = naked.__qualname__.split('.')[0]
    module = getattr(naked, '__module__', _marker)
    if module is _marker:
        return name
    return '%s.%s' % (module, name)


def isReferencable(path):
    """Return whether the Python path is referencable."""
    # Sometimes no path exists, so make a simple check first; example: None
    if path is None:
        return False

    # There are certain paths that we do not want to reference, most often
    # because they are outside the scope of this documentation
    for exclude_name in IGNORE_MODULES:
        if path.startswith(exclude_name):
            return False
    split_path = path.rsplit('.', 1)
    if len(split_path) == 2:
        module_name, obj_name = split_path
    else:
        module_name, obj_name = split_path[0], None

    # Do not allow private attributes to be accessible
    if (obj_name is not None and
            obj_name.startswith('_') and
            not (obj_name.startswith('__') and obj_name.endswith('__'))):
        return False
    module = safe_import(module_name)
    if module is None:
        return False

    # If the module imported correctly and no name is provided, then we are
    # all good.
    if obj_name is None:
        return True

    obj = getattr(module, obj_name, _marker)
    if obj is _marker:
        return False
    # Detect singeltons; those are not referencable in apidoc (yet)
    if hasattr(obj, '__class__') and getPythonPath(obj.__class__) == path:
        return False
    return True


def _evalId(id):
    if isinstance(id, Global):
        id = id.__name__
        if id == 'CheckerPublic':
            id = 'zope.Public'
    return id


def getPermissionIds(name, checker=_marker, klass=_marker):
    """Get the permissions of an attribute."""
    assert (klass is _marker) != (checker is _marker)
    entry = {}

    if klass is not _marker:
        checker = getCheckerForInstancesOf(klass)

    if checker is not None and INameBasedChecker.providedBy(checker):
        entry['read_perm'] = _evalId(checker.permission_id(name)) \
            or _('n/a')
        entry['write_perm'] = _evalId(checker.setattr_permission_id(name)) \
            or _('n/a')
    else:
        entry['read_perm'] = entry['write_perm'] = None

    return entry


def getFunctionSignature(func):
    """Return the signature of a function or method."""
    if not isinstance(func, (types.FunctionType, types.MethodType)):
        raise TypeError("func must be a function or method")
    result = str(inspect.signature(func))
    result = result.replace("(self)", "()").replace("(self, ", '(')
    return result


def getPublicAttributes(obj):
    """Return a list of public attribute names."""
    attrs = []
    for attr in dir(obj):
        if attr.startswith('_'):
            continue

        try:
            getattr(obj, attr)
        except AttributeError:
            continue

        attrs.append(attr)

    return attrs


def getInterfaceForAttribute(name, interfaces=_marker, klass=_marker,
                             asPath=True):
    """Determine the interface in which an attribute is defined."""
    if (interfaces is _marker) and (klass is _marker):
        raise ValueError("need to specify interfaces or klass")
    if (interfaces is not _marker) and (klass is not _marker):
        raise ValueError("must specify only one of interfaces and klass")

    if interfaces is _marker:
        direct_interfaces = list(implementedBy(klass))
        interfaces = {}
        for interface in direct_interfaces:
            interfaces[interface] = 1
            for base in interface.getBases():
                interfaces[base] = 1
        interfaces = interfaces.keys()

    for interface in interfaces:
        if name in interface.names():
            if asPath:
                return getPythonPath(interface)
            return interface

    return None


def columnize(entries, columns=3):
    """Place a list of entries into columns."""
    if len(entries) % columns == 0:
        per_col = len(entries) // columns
        last_full_col = columns
    else:
        per_col = len(entries) // columns + 1
        last_full_col = len(entries) % columns
    columns = []
    col = []
    in_col = 0
    for entry in entries:
        if in_col < per_col - int(len(columns)+1 > last_full_col):
            col.append(entry)
            in_col += 1
        else:
            columns.append(col)
            col = [entry]
            in_col = 1
    if col:
        columns.append(col)
    return columns


_format_dict = {
    'plaintext': 'zope.source.plaintext',
    'structuredtext': 'zope.source.stx',
    'restructuredtext': 'zope.source.rest'
}


def getDocFormat(module):
    """Convert a module's __docformat__ specification to a renderer source
    id"""
    format = getattr(module, '__docformat__', 'structuredtext').lower()
    # The format can also contain the language, so just get the first part
    format = format.split(' ')[0]
    return _format_dict.get(format, 'zope.source.stx')


def dedentString(text):
    """Dedent the docstring, so that docutils can correctly render it."""
    dedent = min([len(match) for match in space_re.findall(text)] or [0])
    return re.compile('\n {%i}' % dedent, re.M).sub('\n', text)


def renderText(text, module=None, format=None, dedent=True):
    if not text:
        return u''

    if module is not None:
        if isinstance(module, (str, unicode)):
            module = sys.modules.get(module, None)
        if format is None:
            format = getDocFormat(module)

    if format is None:
        format = 'zope.source.rest'

    assert format in _format_dict.values()

    text = dedentString(text)

    if not isinstance(text, unicode):
        text = text.decode('latin-1', 'replace')
    source = createObject(format, text)

    renderer = getMultiAdapter((source, TestRequest()))
    return renderer.render()
