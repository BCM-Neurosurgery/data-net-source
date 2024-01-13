from parsers.WatchParser import WatchParser

test = WatchParser(
    source=None,
    middle=r'D:\Work\DataNet\TestData\parsers\rune_parser',
    target=r'D:\Work\DataNet\TestData\lake\rune'
)

test.check()
