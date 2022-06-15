import parsers

folder_path = r'/Users/raphaelb/Documents/UW/Research/gridlab/optimal/data/rcs07/rcs/combined_original'
myRCSParser = parsers.RCSParser(folder_path)
myRCSParser.full_parse()