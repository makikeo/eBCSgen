import itertools
import random
from copy import copy, deepcopy

from Core import Rate
from Core.Complex import Complex
from Core.Side import Side
from Core.Reaction import Reaction


def column(lst, index):
    return tuple(map(lambda x: x[index], lst))


class Rule:
    def __init__(self, agents: tuple, mid: int, compartments: list, complexes: list, pairs: list, rate: Rate):
        """
        Class to represent BCSL rule

        :param agents: tuple of Atomic/Structure agents in the order as given by the rule
        :param mid: index of first agent from right-hand side
        :param compartments: list assigning to each position a compartment (for each agent)
        :param complexes: list of pairs (from, to) indicating where the complex starts and ends
        :param pairs: entangled agents from LHS to RHS
        :param rate: string representing expression
        """
        self.agents = agents
        self.mid = mid
        self.compartments = compartments
        self.complexes = complexes
        self.pairs = pairs
        self.rate = rate
        self.comment = (False, [])

    def __eq__(self, other: 'Rule'):
        return self.agents == other.agents and self.mid == other.mid and self.compartments == other.compartments and \
               self.complexes == other.complexes and self.pairs == other.pairs and str(self.rate) == str(other.rate)

    def __repr__(self):
        return str(self)

    def __str__(self):
        lhs, rhs = self.create_complexes()
        rate = " @ " + str(self.rate) if self.rate else ""
        pre_comment, post_comment = "", ""
        if self.comment[1]:
            comment = "// redundant #{" + ", ".join(list(map(str, self.comment[1]))) + "} "
            pre_comment = comment + "// " if self.comment[0] else ""
            post_comment = " " + comment if not self.comment[0] else ""

        return pre_comment + " + ".join(lhs.to_list_of_strings()) + " => " + " + ".join(rhs.to_list_of_strings()) \
               + rate + post_comment

    def __lt__(self, other):
        return str(self) < str(other)

    def __hash__(self):
        return hash(str(self))

    def create_complexes(self):
        """
        Creates left- and right-hand sides of rule as multisets of Complexes.

        :return: two multisets of Complexes represented as object Side
        """
        lhs, rhs = [], []
        for (f, t) in self.complexes:
            c = Complex(self.agents[f:t + 1], self.compartments[f])
            lhs.append(c) if t < self.mid else rhs.append(c)
        return Side(lhs), Side(rhs)

    def to_reaction(self) -> Reaction:
        """
        Converts Rule to Reactions -> complicated rule structure is simplified to multiset (resp. Side)
        representation of both sides.

        :return: created Reaction
        """
        lhs, rhs = self.create_complexes()
        return Reaction(lhs, rhs, copy(self.rate))

    def rate_to_vector(self, ordering, definitions: dict):
        """
        Converts all occurrences of Complexes in rate to vector representation.

        :param ordering: given ordering of unique of Complexes (as sortedcontainers.SortedList)
        :param definitions: dict of (param_name, value)
        """
        if self.rate:
            self.rate.vectorize(ordering, definitions)

    def create_reactions(self, atomic_signature: dict, structure_signature: dict) -> set:
        """
        Adds context to all agents and generated all possible combinations.
         Then, new rules with these enhances agents are generated and converted to Reactions.

        :param atomic_signature: given mapping of atomic name to possible states
        :param structure_signature: given mapping of structure name to possible atomics
        :return:
        """
        results = []
        for (l, r) in self.pairs:
            if l is None:
                right = -1
                left = self.agents[r]
            elif r is None:
                right = 1
                left = self.agents[l]
            else:
                left = self.agents[l]
                right = self.agents[r]
            results.append(left.add_context(right, atomic_signature, structure_signature))
        reactions = set()
        for result in itertools.product(*results):
            new_agents = tuple(filter(None, column(result, 0) + column(result, 1)))
            new_rule = Rule(new_agents, self.mid, self.compartments, self.complexes, self.pairs, self.rate)
            reactions.add(new_rule.to_reaction())
        return reactions

    def compatible(self, other: 'Rule') -> bool:
        """
        Checks whether Rule is compatible (position-wise) with the other Rule.
        Is done by formaly translating to Reactions (just a better object handling).

        :param other: given Rule
        :return: True if compatible
        """
        self_reaction = self.to_reaction()
        other_reaction = other.to_reaction()
        return self_reaction.compatible(other_reaction)

    def reduce_context(self):
        """
        Reduces context of Rule to minimum.
        Includes both agents and Rate.

        :return: new Rule with reduced context
        """
        new_agents = tuple([agent.reduce_context() for agent in self.agents])
        new_rate = self.rate.reduce_context() if self.rate else None
        return Rule(new_agents, self.mid, self.compartments, self.complexes, self.pairs, new_rate)

    def is_meaningful(self) -> bool:
        """
        Checks whether the Rule does any change, i.e. is meaningful.
        Done by translating to Reaction and comparing its sides.

        :return: True if meaningful
        """
        reaction = self.to_reaction()
        return not reaction.lhs == reaction.rhs

    def exists_compatible_agent(self, agent: Complex) -> bool:
        """
        Checks whether there exists a compatible agent in the rhs of the rule.

        :param agent: given Complex agent
        :return: True if exists compatible
        """
        reaction = self.to_reaction()
        return reaction.rhs.exists_compatible_agent(agent)

    def create_all_compatible(self, atomic_signature: dict, structure_signature: dict):
        """
        Creates all fully specified complexes for all both Sides

        :param atomic_signature: given atomic signature
        :param structure_signature: given structure signature
        :return: set of all created Complexes
        """
        return self.to_reaction().create_all_compatible(atomic_signature, structure_signature)

    def create_matching_map(self, state):
        self.matching_map = []
        for lhs_complex in self.lhs.agents:
            matches = set()
            for state_complex in list(state):
                if lhs_complex.compatible(state_complex):
                    matches.add(state_complex)
            self.matching_map.append(matches)

    def update_matching_map(self, change):
        pass

    def evaluate_rate(self, state, params):
        agents, _ = self.rate.get_params_and_agents()
        values = dict()
        for (state_complex, count) in state.items():
            for agent in agents:
                if agent.compatible(state_complex):
                    values[agent] = count
        return self.rate.evaluate_direct(values, params)

    def is_applicable(self):
        return [] not in self.matching_map

    def choose_a_match(self, state, all=False):
        if self.is_applicable():
            choices = find_all_matches(deepcopy(self.matching_map), deepcopy(state))
            if choices:
                if not all:
                    return random.choice(choices)
                else:
                    return choices
        return None

    def apply(self, match):
        # TODO: implement apply
        print('CHOSEN:', self)
        print('MATCH:', match)


def find_all_matches(matching_map, state):
    choices = []
    if len(matching_map) == 0:
        return [choices]
    for match in matching_map[0]:
        if match in state and state[match] > 0:
            state[match] -= 1
            for branch in find_all_matches(matching_map[1:], deepcopy(state)):
                choices.append([match] + branch)
    return choices
