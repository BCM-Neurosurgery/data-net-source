import inspect
from source import checkers
from source import uploaders

from source.checkers.base import BaseChecker
from source.uploaders.base import BaseUploader


def get_classes(module, base_class):
    classes = {}
    for name, obj in inspect.getmembers(module):
        if inspect.isclass(obj):
            if issubclass(obj, base_class):
                classes[name] = obj
            else:
                print(f'Skipping {name}')
        elif inspect.ismodule(obj) and 'source.' in str(obj) and 'base' not in str(obj):
            print(f'Stepping into {obj}')
            classes_within = get_classes(obj, base_class)
            classes[name] = classes_within

    return classes


def make_init(checker, uploader, transformer=None, **others):
    """Combine the init stubs for each part of the parser"""
    spacer = '\n\n'
    init = '[parser.init.checker]' + checker.init_stub
    if transformer:
        init += spacer + '[parser.init.transformer]\n' + transformer.init_stub
    init += spacer + '[parser.init.uploader]\n' + uploader.init_stub
    for family, other_mixin in others:
        init += spacer + f'[parser.init.{family}]\n' + other_mixin.init_stub
    return init


if __name__ == "__main__":

    all_checkers = get_classes(checkers, BaseChecker)
    all_uploaders = get_classes(uploaders, BaseUploader)
    print(all_checkers)