from __future__ import annotations
from enum import StrEnum
from typing import Union, Sequence, TypeVar, Type, Generic
from abc import ABC, abstractmethod
from random import Random

VERBOSE = 0

class Config():
    MIN_AGE=0
    MAX_AGE=100
    MINIMUM_PARENT_AGE=18

T = TypeVar("T", bound="BaseStrEnum")
class BaseStrEnum(StrEnum):
    @classmethod
    def values(cls: Type[T]) -> list[T]:
        return list(cls)

# tells you exactly who that person is
class ConcreteRelation(BaseStrEnum):
    FATHER="father"
    MOTHER="mother"
    GRANDFATHER="grandfather"
    GRANDMOTHER="grandmother"

# can have more than one candidate (superposition)
class AbstractRelation(BaseStrEnum):
    PARENT="parent"
    BROTHER="brother"
    SISTER="sister"
    CHILD="child"
    SON="son"
    DAUGHTER="daughter"
    STEP_BROTHER="step_brother"
    STEP_SISTER="step_sister"
    SIBLING="sibling"
    COUSIN="cousin"
    GRANDPARENT="grandparent"
    UNCLE="uncle"
    AUNT="aunt"

class Gender(BaseStrEnum):
    MALE="male"
    FEMALE="female"

Relation = Union[ConcreteRelation, AbstractRelation]

# class Pointer(ABC):
#     @abstractmethod
#     def reassign_ref(self, person: Person) -> None:
#         pass

#     @abstractmethod
#     def get_ref(self) -> Person:
#         pass

#     @abstractmethod
#     def copy(self) -> Pointer:
#         pass

#     @abstractmethod
#     def __str__(self) -> str:
#         pass

# class SelfPointer(Pointer):
#     def __init__(self, person: Person) -> None:
#         self.person = person
    
#     def reassign_ref(self, person: Person) -> None:
#         self.person = person

#     def get_ref(self) -> Person:
#         return self.person

#     def copy(self) -> SelfPointer:
#         return SelfPointer(self.person)
    
#     def __str__(self) -> str:
#         return f"<id: {self.person.id}>"
    
# class OtherPointer(Pointer):
#     def __init__(self, concrete_relation: ConcreteRelation, pointer: Pointer) -> None:
#         self.concrete_relation = concrete_relation
#         self.pointer = pointer
    
#     def reassign_ref(self, person: Person) -> None:
#         self.pointer.reassign_ref(person)
    
#     def get_ref(self) -> Person:
#         return self.pointer.get_ref()

#     def copy(self) -> OtherPointer:
#         return OtherPointer(self.concrete_relation, self.pointer.copy())
    
#     def __str__(self) -> str:
#         return f"{self.concrete_relation} of {self.pointer.__str__()}"

E = TypeVar("E")
class SuperPosition(ABC, Generic[E]):
    @abstractmethod
    def is_valid(self) -> bool:
        pass

    @abstractmethod
    def collapse(self, rnd: Random, **kwargs) -> None:
        pass

class SuperList(SuperPosition[E]):
    def __init__(self, possible_values: list[E]) -> None:
        self.possible_values = possible_values
        self.is_collapsed = False
        self.value = None
    
    def is_valid(self) -> bool:
        return len(self.possible_values) > 0
    
    def collapse(self, rnd: Random, default: E|None=None, **kwarsg) -> None:
        self.is_collapsed = True
        self.value = rnd.choice(self.possible_values) if self.is_valid() else default
        if self.is_valid():
            self.possible_values = [self.value]
    
    def get(self) -> E|None:
        return self.value
    
    def remove(self, value: E):
        if value in self.possible_values:
            self.possible_values.remove(value)
    
    def __str__(self) -> str:
        if self.is_collapsed:
            return f"{self.get()}"
        return f"<{', '.join([str(val) for val in self.possible_values])}>"

class SuperRange(SuperPosition[int]):
    def __init__(self, min: int, max: int) -> None:
        self.min = min
        self.max = max
        self.is_collapsed = False
        self.value = None
    
    def is_valid(self) -> bool:
        return self.min <= self.max
    
    def collapse(self, rnd: Random, default: int=-1, **kwargs) -> None:
        self.is_collapsed = True
        self.value = rnd.randint(self.min, self.max) if self.is_valid() else default
        if self.is_valid():
            self.min = self.value
            self.max = self.value
    
    def get(self) -> int|None:
        return self.value
    
    def smaller_than(self, value: int):
        self.max = min(self.max, value)

    def bigger_than(self, value: int):
        self.min = max(self.min, value)
    
    def __str__(self) -> str:
        if self.is_collapsed:
            return f"{self.get()}"
        return f"<{self.min}...{self.max}>"

class Person(SuperPosition):
    def __init__(self, id: int, name: str|None,
                 father: SuperList[int], mother: SuperList[int],
                 gender: SuperList[Gender], age: SuperRange
        ) -> None:
        self.id = id
        self.name = name
        self.father = father
        self.mother = mother
        self.gender = gender
        self.age = age
    
    def is_valid(self) -> bool:
        return self.father.is_valid() and self.mother.is_valid() and\
            self.gender.is_valid() and self.age.is_valid()
    
    def is_collapsed(self) -> bool:
        return self.name is not None and self.father.is_collapsed and self.mother.is_collapsed\
            and self.gender.is_collapsed and self.age.is_collapsed
    
    def collapse(self, rnd: Random, population:Population|None=None, **kwargs) -> None:
        self.name = Person.get_random_name(rnd)
        self.father.collapse(rnd, None)
        assert population is not None
        father = self.father.get()
        if father is not None:
            self.mother.remove(father)
            father_age = population.people[father].age.get()
            if father_age is not None:
                self.age.smaller_than(father_age - Config.MINIMUM_PARENT_AGE)
        mother = self.mother.get()
        if mother is not None:
            mother_age = population.people[mother].age.get()
            if mother_age is not None:
                self.age.smaller_than(mother_age - Config.MINIMUM_PARENT_AGE)
        self.mother.collapse(rnd, None)
        self.gender.collapse(rnd, None)
        self.age.collapse(rnd, 123)
    
    @staticmethod
    def get_empty(id: int, n: int) -> Person:
        return Person(id, None,
                      SuperList([i for i in range(n) if i != id]),
                      SuperList([i for i in range(n) if i != id]),
                      SuperList(Gender.values()), SuperRange(Config.MIN_AGE, Config.MAX_AGE))
    
    def copy(self) -> Person:
        return Person(self.id, self.name,
            SuperList([f for f in self.father.possible_values if f is not None]),
            SuperList([m for m in self.mother.possible_values if m is not None]),
            SuperList([g for g in self.gender.possible_values if g is not None]),
            SuperRange(self.age.min, self.age.max))
    
    def is_invalid_parent(self, expected_gender: Gender, child: Person):
        if expected_gender == Gender.MALE and self.id not in child.father.possible_values:
            return False
        if expected_gender == Gender.FEMALE and self.id not in child.mother.possible_values:
            return False
        if expected_gender not in self.gender.possible_values:
            return True
        if child.age.min + Config.MINIMUM_PARENT_AGE > self.age.max:
            return True
        return False
    
    @staticmethod
    def get_random_name(rnd: Random):
        import string
        vowels = [v for v in "aeiou"]
        consonants = [s for s in string.ascii_lowercase if s not in vowels]
        vclusters = vowels + ["ae", "ou", "ea", "ai", "io", "ui"]
        cclusters = consonants + ["br", "cr", "dr", "gr", "pr", "fr", "st", "tr"]
        pattern: list[list[str]] = rnd.choice([
            [vowels, consonants, vowels],
            [vowels, consonants, vclusters, consonants],
            [cclusters, vclusters, consonants],
            [cclusters, vclusters, consonants, vowels],
            [cclusters, vclusters, consonants, vowels, consonants],
        ])

        return ''.join([rnd.choice(l) for l in pattern])
    
    def __str__(self) -> str:
        return f"{self.id}: {self.name}\n" +\
            f"father: {str(self.father)}\n" +\
            f"mother: {str(self.mother)}\n" +\
            f"gender: {str(self.gender)}\n" +\
            f"age: {str(self.age)}"
    
    def short_str(self) -> str:
        return f"{self.id}: {self.name} ({str(self.age)}{str(self.gender)})"

class Population:
    def __init__(self, people: Sequence[Person]) -> None:
        self.people = people
        # TODO events
    
    @staticmethod
    def make_empty(count: int) -> Population:
        people: list[Person] = []
        for i in range(count):
            people.append(Person.get_empty(i, count))
        return Population(people)
    
    def copy(self) -> Population:
        people = [person.copy() for person in self.people]
        return Population(people)
    
    def __str__(self) -> str:
        return f"Population({len(self.people)})\n" + "\n".join([str(person) for person in self.people])
    
    def selection(self, rnd: Random) -> Person|None:
        remaining = [person for person in self.people if not person.is_collapsed()]
        if len(remaining) == 0:
            return None
        return rnd.choice(remaining)
    
    def propagate(self, person: Person) -> None:
        if VERBOSE > 0: input(f"propagating {person.id}")
        father, mother, age = person.father.get(), person.mother.get(), person.age.get()
        if father is not None:
            self.people[father].gender.remove(Gender.FEMALE)
            if age is not None:
                self.people[father].age.bigger_than(age + Config.MINIMUM_PARENT_AGE)
        if mother is not None:
            self.people[mother].gender.remove(Gender.MALE)
            if age is not None:
                self.people[mother].age.bigger_than(age + Config.MINIMUM_PARENT_AGE)
        todo = set()
        for other in self.people:
            if other.is_invalid_parent(Gender.MALE, person):
                person.father.remove(other.id)
                if VERBOSE > 0: print(f"*removed from {person.id}")
                todo.add(person)
            if other.is_invalid_parent(Gender.FEMALE, person):
                person.mother.remove(other.id)
                if VERBOSE > 0: print(f"*removed from {person.id}")
                todo.add(person)
            if person.is_invalid_parent(Gender.MALE, other):
                other.father.remove(person.id)
                if VERBOSE > 0: print(f"removed from {other.id}")
                todo.add(other)
            if person.is_invalid_parent(Gender.FEMALE, other):
                other.mother.remove(person.id)
                if VERBOSE > 0: print(f"removed from {other.id}")
                todo.add(other)
        if VERBOSE > 0: print(str(self))
        for other in todo:
            self.propagate(other)

    def collapse(self, rnd: Random) -> None:
        while True:
            person = self.selection(rnd)
            if person is None:
                return
            if VERBOSE > 0: input(f"{person.id} is selected")
            person.collapse(rnd, self)
            if VERBOSE > 0: print(str(self))
            self.propagate(person)
            if VERBOSE > 0: print(str(self))
    
    def get_tree(self, rnd: Random) -> str:
        trio: list[tuple[int, int, int]] = []
        trio_by_father: dict[int, list[tuple[int, int]]] = dict([(person.id, []) for person in self.people])
        trio_by_mother: dict[int, list[tuple[int, int]]] = dict([(person.id, []) for person in self.people])
        for person in self.people:
            father, mother = person.father.get(), person.mother.get()
            if father is not None and mother is not None:
                trio.append((father, mother, person.id))
                trio_by_father[father].append((mother, person.id))
                trio_by_mother[mother].append((father, person.id))
        horizontal_order = []
        horizontal_score: list[float] = [i for i in range(len(self.people))]
        for _ in range(1000 * len(self.people)):
            for father, mother, child in trio:
                if horizontal_score[child] > max(horizontal_score[mother], horizontal_score[father]) or\
                    horizontal_score[child] < min(horizontal_score[mother], horizontal_score[father]):
                    horizontal_score[child] = rnd.random() *\
                        abs(horizontal_score[father] - horizontal_score[mother]) +\
                        min(horizontal_score[father], horizontal_score[mother])
        horizontal_order = [i for i in range(len(self.people))]
        horizontal_order.sort(key=lambda i: horizontal_score[i])
        # for father, _, _ in trio:
        #     if father not in horizontal_order:
        #         horizontal_order.append(father)
        #         for mother, child in trio_by_father[father]:
        #             if child not in horizontal_order:
        #                 horizontal_order.append(child)
        #             if mother not in horizontal_order:
        #                 for father2, child2 in trio_by_mother[mother]:
        #                     if father2 not in horizontal_order:
        #                         horizontal_order.append(father2)
        #                     if child2 not in horizontal_order:
        #                         horizontal_order.append(child2)
        #                 horizontal_order.append(mother)
        for i in range(len(self.people)):
            if i not in horizontal_order:
                horizontal_order.append(i)
        vertical_order: dict[int, int] = {}
        sorted_people = [person for person in self.people]
        sorted_people.sort(key=lambda person: person.age.get() or Config.MAX_AGE * 2, reverse=True)
        max_vertical_order = 0
        for person in sorted_people:
            father, mother = person.father.get(), person.mother.get()
            mother_order = vertical_order.get(mother, -1) if mother is not None else -1
            father_order = vertical_order.get(father, -1) if father is not None else -1
            vertical_order[person.id] = max(mother_order, father_order) + 1
            max_vertical_order = max(vertical_order[person.id], max_vertical_order)
        char_per_person = len(str(len(self.people) - 1)) + 2
        # lines: list[list[str]] = [[" " for _ in range(char_per_person * len(self.people))]
        #                     for _ in range(max_vertical_order + 1)]
        # for index, id in enumerate(horizontal_order):
        #     offset = index * char_per_person + 1
        #     id_str = str(id)
        #     line_index = vertical_order[id]
        #     for i in range(len(id_str)):
        #         lines[line_index][offset + i] = id_str[i]
        # return "\n".join(["".join(char for char in line) for line in lines])
        lines: list[list[str]] = [[" " for _ in range(char_per_person * len(self.people))]
                                  for _ in range(len(self.people))]
        positions: list[tuple[int, int, int]] = []
        vpos: dict[int, int] = {}
        hpos: dict[int, int] = {}
        for index, id in enumerate(horizontal_order):
            positions.append((vertical_order[id], index, id))
        positions.sort()
        for line_id, (vindex, hindex, id) in enumerate(positions):
            hoffset = hindex * char_per_person + 1
            id_str = str(id)
            for i in range(len(id_str)):
                lines[line_id][hoffset + i] = id_str[i]
            vpos[id] = line_id
            hpos[id] = hoffset
        for father, mother, child in trio:
            # assert vpos[child] > vpos[father] and vpos[child] > vpos[mother]
            # assert hpos[child] > hpos[father] and hpos[child] < hpos[mother]
            def add_char(x, y, char):
                values = list(set([lines[x][y], char]))
                new = "?"
                if len(values) == 1:
                    new = values[0]
                if " " in values:
                    new = char
                if "┼" in values:
                    new = "┼"
                if "─" in values:
                    if "┘" in values or "└" in values or "┴" in values: 
                        new = "┴"
                    if "┬" in values:
                        new = "┬"
                    if "│" in values or "┤" in values or "├" in values:
                        new = "┼"
                if "│" in values:
                    if "└" in values or "├" in values:
                        new = "├"
                    if "┘" in values or "┤" in values:
                        new = "┤"
                    if "┴" in values or "┬" in values:
                        new = "┼"
                if "┴" in values:
                    if "┘" in values or "└" in values:
                        new = "┴"
                    if "┤" in values or "├" in values or "┬" in values:
                        new = "┼"
                if "┘" in values:
                    if "└" in values:
                        new = "┴"
                    if "┤" in values:
                        new = "┤"
                    if "├" in values or "┬" in values:
                        new = "┼"
                if "└" in values:
                    if "┤" in values or "┬" in values:
                        new = "┼"
                    if "├" in values:
                        new = "├"
                if "┤" in values:
                    if "├" in values or "┬" in values:
                        new = "┼"
                if "├" in values and "┬" in values:
                        new = "┼"
                if new == "?":
                    print(values)
                lines[x][y] = new
            higher = mother if vpos[mother] < vpos[father] else father
            lower = mother if higher == father else father
            hmin = (hpos[father] + len(str(father))) if hpos[father] < hpos[mother] else\
                (hpos[mother] + len(str(mother)))
            hmax = hpos[father] if hpos[father] > hpos[mother] else hpos[mother]
            for i in range(hmin, hmax):
                add_char(vpos[lower], i, "─")
            if hpos[higher] < hpos[lower]:
                descend_hpos = hpos[higher] + len(str(higher)) - 1
                add_char(vpos[lower], descend_hpos, "└")
            else:
                descend_hpos = hpos[higher]
                add_char(vpos[lower], descend_hpos, "┘")
            for i in range(vpos[higher] + 1, vpos[lower]):
                add_char(i, descend_hpos, "│")
            add_char(vpos[lower], hpos[child], "┬")
            for i in range(vpos[lower] + 1, vpos[child]):
                add_char(i, hpos[child], "│")
        return "\n".join(["".join(char for char in line) for line in lines])
    
def main():
    population = Population.make_empty(20)
    print(population)
    population.collapse(Random(13))
    print(population)
    print(population.get_tree(Random(43)))

if __name__ == "__main__":
    main()
