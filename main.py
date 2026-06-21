from pathlib import Path

from utils.parser import ParsedQuery
from utils.schema import Database 
from sys import argv

def main(*sysargv):
    first_element = sysargv[0]
    m = Database(first_element)
    print(m)
    quary = input()
    q = ParsedQuery(quary)
    print(q)
    

if __name__ == "__main__":
    main(*argv[1:])