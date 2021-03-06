import logging
import string
from itertools import chain
from typing import Dict, NamedTuple, Set, Tuple, TextIO

logger = logging.getLogger(__name__)


class CFG(NamedTuple):
    initial_symbol: str
    productions: Dict[str, Set[str]]
    nonterminals: Set[str]
    terminals: Set[str]

    def first(self, sentence: str, visited=set()) -> Set[str]:
        first = set()
        visited |= {sentence}

        # compute transitive closure of first(yn)
        for y in sentence.split():
            # first of terminal is itself
            if y not in self.nonterminals:
                visited -= {sentence}
                return first | {y}

            first_y = set()
            for x in self.productions[y]:
                if x not in visited:
                    first_y |= self.first(x)

            first |= (first_y - {'&'})

            if '&' not in first_y:
                visited -= {sentence}
                return first

        visited -= {sentence}

        # if for never breaks, & in first(yk)
        return first | {'&'}

    def first_nonterminal(self, symbol: str, visited=set()) -> Set[str]:
        if symbol in self.terminals:
            return set()

        if symbol == '&':
            return {symbol}

        visited |= {symbol}

        first = set()
        if '&' in self.productions[symbol]:
            first |= {'&'}

        for production in (p.split() for p in self.productions[symbol]):
            # compute transitive closure of first_nonterminal(yn)
            for y in production:
                if y in self.nonterminals:
                    first |= {y}

                if y in visited:
                    continue
                first_y = self.first_nonterminal(y, visited=visited)
                first |= (first_y - {'&'})

                if '&' not in first_y:
                    break

            # if for never breaks, & in first(yk)
            else:
                first |= {'&'}

        visited -= {symbol}

        return first

    def follow(self, symbol: str, visited=set()) -> Set[str]:
        ret = set()
        visited |= {symbol}

        if symbol == self.initial_symbol:
            ret |= {'$'}

        for k, v in self.productions.items():
            for production in (p.split() for p in v):
                piece = production
                while symbol in piece:
                    piece = piece[production.index(symbol) + 1:]

                    for y in piece:
                        first = self.first(y)#, visited=visited | {y})
                        ret |= (first - {'&'})

                        if '&' not in first:
                            break

                    # if for never breaks, symbol might be last of production
                    else:
                        if symbol != k and k not in visited:
                            ret |= self.follow(k, visited=visited)

        visited -= {symbol}
        return ret

    def is_ll1(self) -> bool:
        def has_left_recursion() -> bool:
            for x in self.nonterminals:
                if x in self.first_nonterminal(x):
                    return True
            return False

        def is_factored() -> bool:
            for y in self.productions.values():
                if len(y) != len(set(production[0] for production in y)):
                    return False
            return True

        def has_ambiguity():
            for x in self.nonterminals:
                first = self.first(x)
                if '&' not in first:
                    continue

                if first & self.follow(x):
                    return True
            return False

        return not has_left_recursion() and is_factored() and not has_ambiguity()

    def parse_table(self) -> Dict[Tuple[str, str], str]:
        table = {}

        for nt, p in ((x, y) for x, v in self.productions.items() for y in v):
            for symbol in p.split():
                first = self.first(symbol)

                for t in (first - {'&'}):
                    table[(nt, t)] = p

                if '&' not in first:
                    break
            else:
                for t in self.follow(nt):
                    table[(nt, t)] = p

        return table

    def parse(self, sentence: str):
        table = self.parse_table()

        sentence = sentence.split() + ['$']
        stack = ['$', self.initial_symbol]

        yield sentence[:-1], stack[1:]

        while True:
            front, top = sentence[0], stack.pop()

            # we stacked empty symbol
            if top == '&':
                continue

            # sentence is over
            if top == front == '$':
                break

            if top in self.terminals:
                if top != front:
                    raise ValueError(f'{top} != {front}')

                _, *sentence = sentence

            else:
                rule = table.get((top, front))
                if rule:
                    if rule != '&':
                        stack.extend(reversed(rule.split()))

                else:
                    raise ValueError(f'there is no ({top}, {front}) in parse table')

            yield sentence[:-1], stack[1:]

    def without_infertile(self):
        def fertile(ni):
            for symbol in ni:
                yield symbol

            allowed = ni | self.terminals | {'&'}
            for symbol, productions in self.productions.items():
                for ys in (set(p.split()) for p in productions):
                    if ys <= allowed:
                        yield symbol

        ni, next_ni = set(), set(fertile(set()))
        while ni != next_ni:
            ni, next_ni = set(next_ni), set(fertile(next_ni))

        fertile = ni | self.terminals | {'&'}
        return self.create(
            initial_symbol=self.initial_symbol,
            productions={
                symbol: {
                    production
                    for production in productions
                    if all(v in fertile for v in production.split())
                }
                for symbol, productions in self.productions.items()
                if symbol in fertile
            }
        )

    def epsilon_free(self):
        for symbol, productions in self.productions.items():
            prod_ = list(productions)
            for destiny in prod_:
                for i, char in enumerate(destiny):
                    if char == ' ':
                        continue
                    if '&' in self.first(char):
                        new_prod = (destiny[:i] + destiny[i:].replace(char, '', 1)).replace('  ', ' ').strip()
                        prod_.append(new_prod)
                        self.productions[symbol] |= {new_prod}

        for symbol, productions in self.productions.items():
            if symbol != self.initial_symbol:
                self.productions[symbol] -= {'&'}
            self.productions[symbol] -= {''}

        initial = self.initial_symbol
        if '&' in self.first(initial):
            self.productions[initial] -= {'&'}
            self.productions[f"{initial}'"] = {initial, '&'}
            initial = f"{initial}'"

        return self.create(
                initial_symbol=initial,
                productions={symbol: p for symbol, p in self.productions.items() if len(p) != 0}
                )

    def __str__(self):
        alphabet = self.initial_symbol + string.ascii_letters + '&'

        def key(word):
            return [alphabet.index(c) for c in word.split()]

        output = []
        for symbol in [self.initial_symbol] + sorted(set(self.productions.keys()) - {self.initial_symbol}, key=key):
            productions = sorted(self.productions[symbol], key=key)
            output.append(f"{symbol} -> {' | '.join(productions)}")

        return "<CFG initial_symbol='{}' productions={{\n\t{}\n}}>".format(
            self.initial_symbol,
            '\n\t'.join(output),
        )

    @classmethod
    def create(cls, initial_symbol: str, productions: Dict[str, Set[str]]):
        nonterminals = set(productions.keys())

        return cls(
            initial_symbol=initial_symbol,
            productions=productions,
            nonterminals=nonterminals,
            terminals={
                symbol
                for production in chain.from_iterable(productions.values())
                for symbol in production.split()
                if symbol != '&' and symbol not in nonterminals
            }
        )

    @classmethod
    def load(cls, fp: TextIO):
        initial_symbol, productions = None, {}

        for line in fp:
            line = line.strip()
            if not line:
                continue

            if '->' not in line:
                logger.warning(f'Invalid line, skipping: {line}')
                continue

            x, y = [s.strip() for s in line.split('->', maxsplit=1)]
            if not x:
                logger.warning(f'Invalid symbol, skipping: {x}')
                continue

            if '->' in y:
                logger.warning(f'Invalid productions, skipping')
                continue

            if not initial_symbol:
                initial_symbol = x

            def filter_productions(productions):
                for p in productions.split('|'):
                    q = p.strip()
                    if not q:
                        logger.warning(f'Empty production, skipping...')
                        continue

                    yield q

            y = set(filter_productions(y))
            if not y:
                logger.warning(f'Symbol with no productions, skipping...')
                continue

            productions[x] = y

        if not initial_symbol:
            raise ValueError('Grammar with no symbols!')

        if not productions:
            raise ValueError('Grammer with no productions!')

        return cls.create(initial_symbol, productions)
