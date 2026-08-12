---
content_unit_id: ml-unit-013
book_id: ml-001
topic_id: ml-course-001
chapter: 强化学习基础
knowledge_points: [prog-python]
source_id: src-ocademy-ml
source_relative_path: open-machine-learning-jupyter-book/prerequisites/python-programming-basics.ipynb
source_commit: b1a5645749b1e3ec9977693b01c662014b71cae5
license: CC-BY-4.0
source_url: https://press.ocademy.cc/prerequisites/python-programming-basics.html
attribution: Open Machine Learning Book — Ocademy community
cleaning_status: approved
review_status: approved
reviewer: content-editorial-v1
reviewed_at: 2026-07-31
review_method: editorial-structure-and-source-audit-v1
---

# 强化学习基础：Python 编程基础

> 本单元依据 Open Machine Learning Book 的固定版本整理；阅读原文、插图与延伸练习请使用页面中的官方章节链接。

## 学习目标

完成本节后，你应能解释并应用：Python。

## 阅读重点

使用 Python 基础语法与数据结构

## 主动回忆检查

不查看资料，尝试用自己的话回答：本节概念解决什么问题？它与前置知识或下一步任务有什么关系？若无法回答，请先完成章节练习，再进行正式复测。

## 原文学习材料

```python
# Install the necessary dependencies

import sys
import os
!{sys.executable} -m pip install --quiet jupyterlab_myst ipython pytest
```

<details>

<summary><b>LICENSE</b></summary>

MIT License

Copyright (c) 2018 Oleksii Trekhleb
Copyright (c) 2018 Real Python

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

</details>

# Python programming basics

## Python syntax

**Python syntax compared to other programming languages**

- Python was designed for readability and has some similarities to the English language with influence from mathematics.
- Python uses new lines to complete a command, as opposed to other programming languages which often use semicolons or parentheses.
- Python relies on indentation, using whitespace, to define scope; such as the scope of loops, functions and classes. Other programming languages often use curly brackets for this purpose.

### Python indentations

While in other programming languages the indentation in code is for readability only, in Python the indentation is very important.

Python uses indentation to indicate a block of code.

```python
if 5 > 2:
    print("Five is greater than two!")
```

Python will give you an error if you skip the indentation.

### Comments

Python has the commenting capability for the purpose of in-code documentation. Comments start with a `#`, and Python will render the rest of the line as a comment:

```python
# This is a comment.
print("Hello, World!")
```

### Docstrings

Python also has extended documentation capability, called docstrings. Docstrings can be one line, or multiline. Docstrings are also comments. Python uses `"""` at the beginning and end of the docstring:

```python
"""This is a 
multiline docstring."""
print("Hello, World!")
```

## Variables

Python is completely object-oriented, and not "statically typed". You do not need to declare variables before using them or declare their type. Every variable in Python is an object. Unlike other programming languages, Python has no command for declaring a variable. A variable is created the moment you first assign a value to it. A variable can have a short name (like x and y) or a more descriptive name (age, carname, total_volume). Rules for Python variables:

- A variable name must start with a letter or the underscore character.
- A variable name cannot start with a number.
- A variable name can only contain alpha-numeric characters and underscores (A-z, 0-9, and _ ).
- Variable names are case-sensitive (age, Age and AGE are three different variables).

```{seealso}
- https://docs.python.org/3/tutorial/introduction.html
- https://www.w3schools.com/python/python_variables.asp
- https://www.learnpython.org/en/Variables_and_Types
```

```python
integer_variable = 5
string_variable = 'John'

assert integer_variable == 5
assert string_variable == 'John'
```

## Operators

Operators are used to performing operations on variables and values. Python divides the operators into the following groups:

- Arithmetic operators
- Assignment operators
- Comparison operators
- Logical operators
- Identity operators
- Membership operators
- Bitwise operators

```{seealso}
- https://www.w3schools.com/python/python_operators.asp
```

### Arithmetic operators

Arithmetic operators are used with numeric values to perform common mathematical operations.

```python
# Addition.
assert 5 + 3 == 8

# Subtraction.
assert 5 - 3 == 2

# Multiplication.
assert 5 * 3 == 15
assert isinstance(5 * 3, int)

# Division.
# Result of division is float number.
assert 5 / 3 == 1.6666666666666667
assert 8 / 4 == 2
assert isinstance(5 / 3, float)
assert isinstance(8 / 4, float)

# Modulus.
assert 5 % 3 == 2

# Exponentiation.
assert 5 ** 3 == 125
assert 2 ** 3 == 8
assert 2 ** 4 == 16
assert 2 ** 5 == 32
assert isinstance(5 ** 3, int)

# Floor division.
assert 5 // 3 == 1
assert 6 // 3 == 2
assert 7 // 3 == 2
assert 9 // 3 == 3
assert isinstance(5 // 3, int)
```

### Comparison operators

Comparison operators are used to compare two values.

```python
# Equal.
number = 5
assert number == 5

# Not equal.
number = 5
assert number != 3

# Greater than.
number = 5
assert number > 3

# Less than.
number = 5
assert number < 8

# Greater than or equal to
number = 5
assert number >= 5
assert number >= 4

# Less than or equal to
number = 5
assert number <= 5
assert number <= 6
```

### Let's visualize it

Let's write a Python program to calculate the discriminant value. It calculates the roots of a quadratic equation of the form ax^2 + bx + c = 0, where a, b, and c are arbitrary numeric values.

The discriminant value is calculated by using the formula (b^2 - 4ac). The discriminant value is used to determine the number of roots of the quadratic equation.

If the discriminant is positive, there are two real solutions to the equation. The program prints the discriminant value and the message "Two Solutions." If the discriminant is zero, there is one real solution to the equation. The program prints the discriminant value and the message "One Solution."

If the discriminant is negative, there are no real solutions to the equation. The program prints the discriminant value and the message "No Real Solutions."

```python
def calculate_discriminant(a, b, c):
    dis = (b**2) - (4*a*c)
    
    formula = f"{a}x^2 + {b}x + {c} = 0"
    
    if dis > 0:
        print(f"Two Solutions for {formula}. Discriminant value is: {dis}")
    elif dis == 0:
        print(f"One Solution for {formula}. Discriminant value is: {dis}")
    elif dis < 0:
        print(f"No Real Solutions for {formula}. Discriminant value is: {dis}")

a = 1
b = 2
c = 3

calculate_discriminant(a, b, c)
```

## Data types

In programming, data type is an important concept. Variables can store data of different types, and different types can do different things. Python has the following data types built in by default, in these categories:

Name | Type
---------|----------
Text Type | `str`
Numeric Types | `int`, `float`, `complex`
Sequence Types | `list`, `tuple`, `range`
Mapping Type | `dict`
Set Types | `set`, `frozenset`
Boolean Type | `bool`
Binary Types | `bytes`, `bytearray`, `memoryview`
None Type | `NoneType`

```{seealso}
- https://docs.python.org/3/tutorial/introduction.html
- https://www.w3schools.com/python/python_datatypes.asp
```

### Numbers (including booleans)

There are three numeric types in Python:

- `int`
- `float`
- `complex`

```{seealso}
- https://docs.python.org/3/tutorial/introduction.html
- https://www.w3schools.com/python/python_numbers.asp
```

#### Integers

Int, or integer, is a whole number, positive or negative, without decimals, of unlimited length.

```python
positive_integer = 1
negative_integer = -3255522
big_integer = 35656222554887711

assert isinstance(positive_integer, int)
assert isinstance(negative_integer, int)
assert isinstance(big_integer, int)
```

#### Booleans

Booleans represent the truth values `False` and `True`. The two objects representing the values `False` and `True` are the only Boolean objects. The Boolean type is a subtype of the integer type, and Boolean values behave like the values 0 and 1, respectively, in almost all contexts, the exception being that when converted to a string, the strings `False` or `True` are returned, respectively.

```python
true_boolean = True
false_boolean = False

assert true_boolean
assert not false_boolean

assert isinstance(true_boolean, bool)
assert isinstance(false_boolean, bool)

# Let's try to cast boolean to string.
assert str(true_boolean) == "True"
assert str(false_boolean) == "False"
```

#### Floats

Float, or "floating point number" is a number, positive or negative, containing one or more decimals.

```python
float_number = 7.0
# Another way of declaring float is using float() function.
float_number_via_function = float(7) 
float_negative = -35.59

assert float_number == float_number_via_function
assert isinstance(float_number, float)
assert isinstance(float_number_via_function, float)
assert isinstance(float_negative, float)
```

Float can also be scientific numbers with an "e" to indicate the power of 10.

```python
float_with_small_e = 35e3
float_with_big_e = 12E4

assert float_with_small_e == 35000
assert float_with_big_e == 120000
assert isinstance(12E4, float)
assert isinstance(-87.7e100, float)
```

#### Complexes

A complex number has two parts, a real part and an imaginary part. Complex numbers are represented as A+Bi or A+Bj, where A is the real part and B is the imaginary part.

```python
complex_number_1 = 5 + 6j
complex_number_2 = 3 - 2j

assert isinstance(complex_number_1, complex)
assert isinstance(complex_number_2, complex)
assert complex_number_1 * complex_number_2 == 27 + 8j
```

#### Number operation

```python
# Addition.
assert 2 + 4 == 6

# Multiplication.
assert 2 * 4 == 8

# Division always returns a floating point number.
assert 12 / 3 == 4.0
assert 12 / 5 == 2.4
assert 17 / 3 == 5.666666666666667

# Modulo operator returns the remainder of the division.
assert 12 % 3 == 0
assert 13 % 3 == 1

# Floor division discards the fractional part.
assert 17 // 3 == 5

# Raising the number to specific power.
assert 5 ** 2 == 25  # 5 squared
assert 2 ** 7 == 128  # 2 to the power of 7

# There is full support for floating point; operators with mixed type operands convert the integer operand to floating point.
assert 4 * 3.75 - 1 == 14.0
```

[comment]: <> (TODO: add visualization code example, e.g. some sample code from https://realpython.com/python-and-operator/)

### Strings and their methods

Besides numbers, Python can also manipulate strings, which can be expressed in several ways. They can be enclosed in single quotes `''` or double quotes `""` with the same result.

```{seealso}
- https://docs.python.org/3/tutorial/introduction.html
- https://www.w3schools.com/python/python_strings.asp
- https://www.w3schools.com/python/python_ref_string.asp
```

```python
# String with double quotes.
name_1 = "John"

# String with single quotes.
name_2 = 'John'

assert name_1 == name_2
assert isinstance(name_1, str)
assert isinstance(name_2, str)
```

#### String type

`\` can be used to escape quotes. Use `\'` to escape the single quote or use double quotes instead.

```python
single_quote_string = 'doesn\'t'
double_quote_string = "doesn't"

assert single_quote_string == double_quote_string
```

`\n` means newline.

```python
multiline_string = 'First line.\nSecond line.'
```

Without `print()`, `\n` is included in the output. But with `print()`, `\n` produces a new line.

```python
assert multiline_string == 'First line.\nSecond line.'
```

Strings can be indexed, with the first character having index 0. There is no separate character type; a character is simply a string of size one. Note that since -0 is the same as 0, negative indices start from -1.

```python
import pytest
word = 'Python'
assert word[0] == 'P'  # First character.
assert word[5] == 'n'  # Fifth character.
assert word[-1] == 'n'  # Last character.
assert word[-2] == 'o'  # Second-last character.
assert word[-6] == 'P'  # Sixth from the end or zeroth from the beginning.

assert isinstance(word[0], str)
```

In addition to indexing, slicing is also supported. While indexing is used to obtain individual characters, slicing allows you to obtain substring.

```python
assert word[0:2] == 'Py'  # Characters from position 0 (included) to 2 (excluded).
assert word[2:5] == 'tho'  # Characters from position 2 (included) to 5 (excluded).
```

Note how the start is always included, and the end is always excluded. This makes sure that `s[:i] + s[i:]` is always equal to `s`:

```python
assert word[:2] + word[2:] == 'Python'
assert word[:4] + word[4:] == 'Python'
```

Slice indices have useful defaults; an omitted first index defaults to zero, and an omitted second index defaults to the size of the string being sliced.

```python
assert word[:2] == 'Py'  # Character from the beginning to position 2 (excluded).
assert word[4:] == 'on'  # Characters from position 4 (included) to the end.
assert word[-2:] == 'on'  # Characters from the second-last (included) to the end.
```

One way to remember how slices work is to think of the indices as pointing between characters, with the left edge of the first character numbered 0. Then the right edge of the last character of a string of `n` characters has index `n`, for example:

|   | P |   | y |   | t |   | h |   | o |   | n |   |
|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
|  0|   |  1|   |  2|   |  3|   |  4|   |  5|   |  6|
| -6|   | -5|   | -4|   | -3|   | -2|   | -1|

Attempting to use an index that is too large will result in an error.

```python
with pytest.raises(Exception):
    not_existing_character = word[42]
    assert not not_existing_character
```

However, out-of-range slice indexes are handled gracefully when used for slicing.

```python
assert word[4:42] == 'on'
assert word[42:] == ''
```

Python strings cannot be changed — they are immutable. Therefore, assigning to an indexed position in the string results in an error:

```python
with pytest.raises(Exception):
    # pylint: disable=unsupported-assignment-operation
    word[0] = 'J'
```

If you need a different string, you should create a new one.

```python
assert 'J' + word[1:] == 'Jython'
assert word[:2] + 'py' == 'Pypy'
```

The built-in function `len()` returns the length of a string.

```python
characters = 'supercalifragilisticexpialidocious'
assert len(characters) == 34
```

String literals can span multiple lines. One way is using triple-quotes: `"""..."""` or `'''...'''`. The end of lines are automatically included in the string, but it’s possible to prevent this by adding a `\` at the end of the line. The following example:

```python
multi_line_string = '''\
    First line
    Second line
'''

assert multi_line_string == '''\
    First line
    Second line
'''
```

#### String operations

Strings can be concatenated (glued together) with the `+` operator, and repeated with `*`.

```python
assert 3 * 'un' + 'ium' == 'unununium'

python = 'Py' 'thon'
assert python == 'Python'
```

This feature is particularly useful when you want to break long strings:

```python
text = (
    'Put several strings within parentheses '
    'to have them joined together.'
)
assert text == 'Put several strings within parentheses to have them joined together.'
```

If you want to concatenate variables or a variable and a literal, use `+`:

```python
prefix = 'Py'
assert prefix + 'thon' == 'Python'
```

#### String methods

```python
hello_world_string = "Hello, World!"
```

The `strip()` method removes any whitespace from the beginning or the end.

```python
string_with_whitespaces = " Hello, World! "
assert string_with_whitespaces.strip() == "Hello, World!"
```

The `len()` method returns the length of a string.

```python
assert len(hello_world_string) == 13
```

The `lower()` method returns the string in lowercase.

```python
assert hello_world_string.lower() == 'hello, world!'
```

The `upper()` method returns the string in the upper case.

```python
assert hello_world_string.upper() == 'HELLO, WORLD!'
```

The `replace()` method replaces a string with another string.

```python
assert hello_world_string.replace('H', 'J') == 'Jello, World!'
```

The `split()` method splits the string into substrings if it finds instances of the separator.

```python
assert hello_world_string.split(',') == ['Hello', ' World!']
```

The `capitalize()` method converts the first character to upper case.

```python
assert 'low letter at the beginning'.capitalize() == 'Low letter at the beginning'
```

The `count()` method returns the number of times a specified value occurs in a string.

```python
assert 'low letter at the beginning'.count('t') == 4
```

The `find()` method searches the string for a specified value and returns the position of where it was found.

```python
assert 'Hello, welcome to my world'.find('welcome') == 7
```

The `title()` method converts the first character of each word to upper case.

```python
assert 'Welcome to my world'.title() == 'Welcome To My World'
```

The `replace()` method returns a string where a specified value is replaced with a specified value.

```python
assert 'I like bananas'.replace('bananas', 'apples') == 'I like apples'
```

The `join()` method joins the elements of an iterable to the end of the string.

```python
my_tuple = ('John', 'Peter', 'Vicky')
assert '-'.join(my_tuple) == 'John-Peter-Vicky'
```

The `isupper()` method returns True if all characters in the string are upper case.

```python
assert 'ABC'.isupper()
assert not 'AbC'.isupper()
```

The `isalpha()` method checks if all the characters in the text are letters.

```python
assert 'CompanyX'.isalpha()
assert not 'Company 23'.isalpha()
```

The `isdecimal()` method returns True if all characters in the string are decimals.

```python
assert '1234'.isdecimal()
assert not 'a21453'.isdecimal()
```

#### String formatting

Often you’ll want more control over the formatting of your output than simply printing space-separated values. There are several ways to format output.

##### Formatted string literals

Formatted string literals (also called f-strings for short) let you include the value of Python expressions inside a string by prefixing the string with `f` or `F` and writing expressions as `{expression}`.

An optional format specifier can follow the expression. This allows greater control over how the value is formatted. The following example rounds pi to three places after the decimal.

```python
pi_value = 3.14159
assert f'The value of pi is {pi_value:.3f}.' == 'The value of pi is 3.142.'
```

Passing an integer after the `:` will cause that field to be a minimum number of characters wide. This is useful for making columns line up.

```python
table_data = {'Sjoerd': 4127, 'Jack': 4098, 'Dcab': 7678}
table_string = ''
for name, phone in table_data.items():
    table_string += f'{name:7}==>{phone:7d}'

assert table_string == (
    'Sjoerd ==>   4127'
    'Jack   ==>   4098'
    'Dcab   ==>   7678')
```

##### The string format() method

Basic usage of the `str.format()` method looks like this:

```python
assert 'We are {} who say "{}!"'.format('knights', 'Ni') == 'We are knights who say "Ni!"'
```

The brackets and characters within them (called format fields) are replaced with the objects passed into the `str.format()` method. A number in the brackets can be used to refer to the position of the object passed into the `str.format()` method.

```python
assert '{0} and {1}'.format('spam', 'eggs') == 'spam and eggs'
assert '{1} and {0}'.format('spam', 'eggs') == 'eggs and spam'
```

If keyword arguments are used in the `str.format()` method, their values are referred to by using the name of the argument.

```python
formatted_string = 'This {food} is {adjective}.'.format(
    food='spam',
    adjective='absolutely horrible'
)

assert formatted_string == 'This spam is absolutely horrible.'
```

Positional and keyword arguments can be arbitrarily combined.

```python
formatted_string = 'The story of {0}, {1}, and {other}.'.format(
    'Bill',
    'Manfred',
    other='Georg'
)

assert formatted_string == 'The story of Bill, Manfred, and Georg.'
```

If you have a really long format string that you don’t want to split up, it would be nice if you could reference the variables to be formatted by name instead of by position. This can be done by simply passing the dict and using square brackets `[]` to access the keys.

```python
table = {'Sjoerd': 4127, 'Jack': 4098, 'Dcab': 8637678}
formatted_string = 'Jack: {0[Jack]:d}; Sjoerd: {0[Sjoerd]:d}; Dcab: {0[Dcab]:d}'.format(table)

assert formatted_string == 'Jack: 4098; Sjoerd: 4127; Dcab: 8637678'
```

This could also be done by passing the table as keyword arguments with the `**` notation.

```python
formatted_string = 'Jack: {Jack:d}; Sjoerd: {Sjoerd:d}; Dcab: {Dcab:d}'.format(**table)

assert formatted_string == 'Jack: 4098; Sjoerd: 4127; Dcab: 8637678'
```

#### Let's visualize it

In this example, every augmented assignment adds a new syllable to the final word using the += operator. The concatenation technique is used in a for loop to construct a string from several strings in a list or any other iterable:

```python
def concatenate(iterable, sep=" "):
    sentence = iterable[0]
    for word in iterable[1:]:
        sentence = sentence + (sep + word)
    return sentence

# Let's try to split and concat a string.
original_string = "Hello, World! I am a Pythonista!"
splitted_string = original_string.split(' ')
print(concatenate(splitted_string))

# Let's try to split and concat a word.
sub_string = splitted_string[1]
splitted_sub_string = sub_string.split()
print(concatenate(splitted_string[1], sep=""))
```

Here, a more comprehensive example of using this concatenation tool is when you need to generate a separator string to use in tabular outputs. For example, say you’ve read a CSV file with information about people into a list of lists.

You can use the star operator (*) to concatenate strings in Python. In this context, this operator is known as the repeated concatenation operator. It works by repeating a string a certain number of times.

```python
def display_table(data):
    max_len = max(len(header) for header in data[0])
    sep = "-" * max_len
    for row in data:
        print("|".join(header.ljust(max_len) for header in row))
        if row == data[0]:
            print("|".join(sep for _ in row))

data = [
   ["Name", "Age", "Hometown"],
   ["Alice", "25", "New York"],
   ["Bob", "30", "Los Angeles"],
   ["Charlie", "35", "Chicago"]
]
display_table(data)
```

### Lists and their methods (including list comprehensions)

Python knows several compound data types, used to group together other values. The most versatile is the list, which can be written as a list of comma-separated values (items) between square brackets. Lists might contain items of different types, but usually, the items all have the same type.

```{seealso}
- https://www.learnpython.org/en/Lists
- https://docs.python.org/3/tutorial/introduction.html
- https://docs.python.org/3/tutorial/datastructures.html#more-on-lists
```

#### List type

Lists are very similar to arrays. They can contain any type of variable, and they can contain as many variables as you wish. Lists can also be iterated over in a very simple manner.

Here is an example of how to build a list.

```python
squares = [1, 4, 9, 16, 25]

assert isinstance(squares, list)
```

Like strings (and all other built-in sequence types), lists can be indexed and sliced:

```python
assert squares[0] == 1  # indexing returns the item
assert squares[-1] == 25
assert squares[-3:] == [9, 16, 25]  # slicing returns a new list
```

All slice operations return a new list containing the requested elements.
This means that the following slice returns a new (shallow) copy of the list:

```python
assert squares[:] == [1, 4, 9, 16, 25]
```

Lists also support operations like concatenation:

```python
assert squares + [36, 49, 64, 81, 100] == [1, 4, 9, 16, 25, 36, 49, 64, 81, 100]
```

Unlike strings, which are immutable, lists are a mutable type, i.e. it is possible to change their content:

```python
cubes = [1, 8, 27, 65, 125]  # something's wrong here, the cube of 4 is 64!
cubes[3] = 64  # replace the wrong value
assert cubes == [1, 8, 27, 64, 125]
```

You can also add new items at the end of the list, by using the `append()` method.

```python
cubes.append(216)  # add the cube of 6
cubes.append(7 ** 3)  # and the cube of 7
assert cubes == [1, 8, 27, 64, 125, 216, 343]
```

Assignment to slices is also possible, and this can even change the size of the list or clear it entirely:

```python
letters = ['a', 'b', 'c', 'd', 'e', 'f', 'g']
letters[2:5] = ['C', 'D', 'E']  # replace some values
assert letters == ['a', 'b', 'C', 'D', 'E', 'f', 'g']
letters[2:5] = []  # now remove them
assert letters == ['a', 'b', 'f', 'g']
```

Clear the list by replacing all the elements with an empty list.

```python
letters[:] = []
assert letters == []
```

The built-in function `len()` also applies to lists.

```python
letters = ['a', 'b', 'c', 'd']
assert len(letters) == 4
```

It is possible to nest lists (create lists containing other lists), for example:

```python
list_of_chars = ['a', 'b', 'c']
list_of_numbers = [1, 2, 3]
mixed_list = [list_of_chars, list_of_numbers]
assert mixed_list == [['a', 'b', 'c'], [1, 2, 3]]
assert mixed_list[0] == ['a', 'b', 'c']
assert mixed_list[0][1] == 'b'
```

#### List methods

```python
import pytest

fruits = ['orange', 'apple', 'pear', 'banana', 'kiwi', 'apple', 'banana', 'grape']
```

`list.remove(x)` removes the first item from the list whose value is equal to x. It raises a `ValueError` if there is no such item.

```python
fruits.remove('grape')
assert fruits == ['orange', 'apple', 'pear', 'banana', 'kiwi', 'apple', 'banana']

with pytest.raises(Exception):
    fruits.remove('not existing element')
```

`list.insert(i, x)` inserts an item at a given position. The first argument is the index of the element before which to insert, so `a.insert(0, x)` inserts at the front of the list, and `a.insert(len(a), x)` is equivalent to `a.append(x)`.

```python
fruits.insert(0, 'grape')
assert fruits == ['grape', 'orange', 'apple', 'pear', 'banana', 'kiwi', 'apple', 'banana']
```

`list.index(x[, start[, end]])` returns a zero-based index in the list of the first item whose value is equal to x. Raises a ValueError if there is no such item. The optional arguments start and end are interpreted as in the slice notation and are used to limit the search to a particular subsequence of the list. The returned index is computed relative to the beginning of the full sequence rather than the start argument.

```python
assert fruits.index('grape') == 0
assert fruits.index('orange') == 1
assert fruits.index('banana') == 4
assert fruits.index('banana', 5) == 7  # Find next banana starting a position 5

with pytest.raises(Exception):
    fruits.index('not existing element')
```

`list.count(x)` returns the number of times x appears in the list.

```python
assert fruits.count('tangerine') == 0
assert fruits.count('banana') == 2
```

`list.copy()` returns a shallow copy of the list. Equivalent to `a[:]`.

```python
fruits_copy = fruits.copy()
assert fruits_copy == ['grape', 'orange', 'apple', 'pear', 'banana', 'kiwi', 'apple', 'banana']
```

`list.reverse()` reverses the elements of the list in place.

```python
fruits_copy.reverse()
assert fruits_copy == [
    'banana',
    'apple',
    'kiwi',
    'banana',
    'pear',
    'apple',
    'orange',
    'grape',
]
```

`list.sort(key=None, reverse=False)` sorts the items of the list in place. (The arguments can be used for sort customization, see `sorted()` for their explanation.)

```python
fruits_copy.sort()
assert fruits_copy == [
    'apple',
    'apple',
    'banana',
    'banana',
    'grape',
    'kiwi',
    'orange',
    'pear',
]
```

`list.pop([i])` removes the item at the given position in the list and returns it. If no index is specified, `a.pop()` removes and returns the last item in the list. (The square brackets around the `i` in the method signature denote that the parameter is optional, not that you should type square brackets at that position.)

```python
assert fruits == ['grape', 'orange', 'apple', 'pear', 'banana', 'kiwi', 'apple', 'banana']
assert fruits.pop() == 'banana'
assert fruits == ['grape', 'orange', 'apple', 'pear', 'banana', 'kiwi', 'apple']
```

`list.clear()` removes all items from the list. Equivalent to `del a[:]`.

```python
fruits.clear()
assert fruits == []
```

#### The del statement

There is a way to remove an item from a list given its index instead of its value: the `del` statement. This differs from the `pop()` method which returns a value. The `del` statement can also be used to remove slices from a list or clear the entire list (which we did earlier by assignment of an empty list to the slice).

```python
import pytest

numbers = [-1, 1, 66.25, 333, 333, 1234.5]

del numbers[0]
assert numbers == [1, 66.25, 333, 333, 1234.5]

del numbers[2:4]
assert numbers == [1, 66.25, 1234.5]

del numbers[:]
assert numbers == []

# del can also be used to delete entire variables:
del numbers
with pytest.raises(Exception):
    # Referencing the name a hereafter is an error (at least until another
    # value is assigned to it).
    assert numbers == []  # noqa: F821
```

#### List comprehensions

List comprehensions provide a concise way to create lists. Common applications are to make new lists where each element is the result of some operations applied to each member of another sequence or iterable or to create a subsequence of those elements that satisfy a certain condition. A list comprehension consists of brackets containing an expression followed by a for clause, then zero or more `for` or `if` clauses. The result will be a new list resulting from evaluating the expression in the context of the `for` and `if` clauses that follow it.

For example, assume we want to create a list of squares, like:

```python
squares = []
for number in range(10):
    squares.append(number ** 2)

assert squares == [0, 1, 4, 9, 16, 25, 36, 49, 64, 81]
```

Note that this creates (or overwrites) a variable named "number" that still exists after the loop completes. We can calculate the list of squares without any side effects using:

```python
squares = list(map(lambda x: x ** 2, range(10)))
assert squares == [0, 1, 4, 9, 16, 25, 36, 49, 64, 81]
```

Or, equivalently (which is more concise and readable):

```python
squares = [x ** 2 for x in range(10)]
assert squares == [0, 1, 4, 9, 16, 25, 36, 49, 64, 81]
```

For example, this list comprehension combines the elements of two lists if they are not equal:

```python
combinations = [(x, y) for x in [1, 2, 3] for y in [3, 1, 4] if x != y]
assert combinations == [(1, 3), (1, 4), (2, 3), (2, 1), (2, 4), (3, 1), (3, 4)]
```

And it’s equivalent to:

```python
combinations = []
for first_number in [1, 2, 3]:
    for second_number in [3, 1, 4]:
        if first_number != second_number:
            combinations.append((first_number, second_number))

assert combinations == [(1, 3), (1, 4), (2, 3), (2, 1), (2, 4), (3, 1), (3, 4)]
```

Note how the order of the `for` and `if` statements is the same in both these snippets.

If the expression is a tuple (e.g. the (x, y) in the previous example), it must be parenthesized. Let's see some more examples:

```python
vector = [-4, -2, 0, 2, 4]
```

Create a new list with the values doubled.

```python
doubled_vector = [x * 2 for x in vector]
assert doubled_vector == [-8, -4, 0, 4, 8]
```

Filter the list to exclude negative numbers.

```python
positive_vector = [x for x in vector if x >= 0]
assert positive_vector == [0, 2, 4]
```

Apply a function to all the elements.

```python
abs_vector = [abs(x) for x in vector]
assert abs_vector == [4, 2, 0, 2, 4]
```

Call a method on each element.

```python
fresh_fruit = ['  banana', '  loganberry ', 'passion fruit  ']
clean_fresh_fruit = [weapon.strip() for weapon in fresh_fruit]
assert clean_fresh_fruit == ['banana', 'loganberry', 'passion fruit']
```

Create a list of 2-tuples like (number, square).

```python
square_tuples = [(x, x ** 2) for x in range(6)]
assert square_tuples == [(0, 0), (1, 1), (2, 4), (3, 9), (4, 16), (5, 25)]
```

Flatten a list using a list comprehension with two `for`.

```python
vector = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
flatten_vector = [num for elem in vector for num in elem]
assert flatten_vector == [1, 2, 3, 4, 5, 6, 7, 8, 9]
```

#### Nested list comprehensions

The initial expression in a list comprehension can be any arbitrary expression, including another list comprehension.

Consider the following example of a 3x4 matrix implemented as a list of 3 lists of length 4:

```python
matrix = [
    [1, 2, 3, 4],
    [5, 6, 7, 8],
    [9, 10, 11, 12],
]
```

The following list comprehension will transpose rows and columns:

```python
transposed_matrix = [[row[i] for row in matrix] for i in range(4)]
assert transposed_matrix == [
    [1, 5, 9],
    [2, 6, 10],
    [3, 7, 11],
    [4, 8, 12],
]
```

As we saw in the previous section, the nested list comprehension is evaluated in the context of the for that follows it, so this example is equivalent to:

```python
transposed = []
for i in range(4):
    transposed.append([row[i] for row in matrix])

assert transposed == [
    [1, 5, 9],
    [2, 6, 10],
    [3, 7, 11],
    [4, 8, 12],
]
```

Which, in turn, is the same as:

```python
transposed = []
for i in range(4):
    # the following 3 lines implement the nested listcomp
    transposed_row = []
    for row in matrix:
        transposed_row.append(row[i])
    transposed.append(transposed_row)

assert transposed == [
    [1, 5, 9],
    [2, 6, 10],
    [3, 7, 11],
    [4, 8, 12],
]
```

In the real world, you should prefer built-in functions to complex flow statements. The `zip()` function would do a great job for this use case.

```python
assert list(zip(*matrix)) == [
    (1, 5, 9),
    (2, 6, 10),
    (3, 7, 11),
    (4, 8, 12),
]
```

#### Let's visualize it

So far, you’ve seen a few tools and techniques to either reverse lists in place or create reversed copies of existing lists. Most of the time, these tools and techniques are the way to go when it comes to reversing lists in Python. For example, Your first approach to iterating over a list in reverse order might be to use reversed().

```python
digits = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]

for digit in reversed(digits):
    print(digit)
```

The second approach to reverse iteration is to use the extended slicing syntax you saw before.

```python
digits = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]

for digit in digits[::-1]:
    print(digit)
```

##### Basic reverse by hand

However, if you ever need to reverse lists by hand, then it’d be beneficial for you to understand the logic behind the process.

```python
digits = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]

def reversed_list(a_list):
    result = []
    for item in a_list:
        result = [item] + result
    return result

reversed_list(digits)
```

Every iteration of the for loop takes a subsequent item from a_list and creates a new list that results from concatenating [item] and result, which initially holds an empty list. The newly created list is reassigned to result. This function doesn’t modify a_list.

##### Insert

```{seealso}
Note: The example above uses a wasteful technique because it creates several lists only to throw them away in the next iteration.
```

```python
digits = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]

def reversed_list(a_list):
    result = []
    for item in a_list:
        result.insert(0, item)
    return result

reversed_list(digits)
```

The call to .insert() inside the loop inserts subsequent items at the 0 index of result. At the end of the loop, you get a new list with the items of a_list in reverse order.

Using .insert() like in the above example has a significant drawback. Insert operations at the left end of Python lists are known to be inefficient regarding execution time. That’s because Python needs to move all the items one step back to insert the new item at the first position.

##### Recursion

You can also use recursion to reverse your lists. Recursion is when you define a function that calls itself. This creates a loop that can become infinite if you don’t provide a base case that produces a result without calling the function again.

You need the base case to end the recursive loop. When it comes to reversing lists, the base case would be reached when the recursive calls get to the end of the input list. You also need to define the recursive case, which reduces all successive cases toward the base case and, therefore, to the loop’s end.

Here’s how you can define a recursive function to return a reversed copy of a given list:

```python
digits = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]

def reversed_list(a_list):
    if len(a_list) == 0:  # Base case
        return a_list
    else:
        # print(a_list)
        # Recursive case
        return reversed_list(a_list[1:]) + a_list[:1]

reversed_list(digits)
```

Inside reversed_list(), you first check the base case, in which the input list is empty and makes the function return. The else clause provides the recursive case, which is a call to reversed_list() itself but with a slice of the original list, a_list[1:]. This slice contains all the items in a_list except for the first item, which is then added as a single-item list (a_list[:1]) to the result of the recursive call.

##### List comprehension

If you’re working with lists in Python, then you probably want to consider using a list comprehension. This tool is quite popular in the Python space because it represents the Pythonic way to process lists.

Here’s an example of how to use a list comprehension to create a reversed list:

```python
digits = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
last_index = len(digits) - 1

[digits[i] for i in range(last_index, -1, -1)]
```

The magic in this list comprehension comes from the call to range(). In this case, range() returns indices from len(digits) - 1 back to 0. This makes the comprehension loop iterate over the items in digits in reverse, creating a new reversed list in the process.

### Tuples

A tuple is a collection that is ordered and unchangeable. In Python, tuples are written with
round brackets.

The Tuples have the following properties:

- You cannot change values in a tuple.
- You cannot remove items in a tuple.

```{seealso}
- https://www.w3schools.com/python/python_tuples.asp
- https://docs.python.org/3/tutorial/datastructures.html#tuples-and-sequences
```

```python
import pytest

fruits_tuple = ("apple", "banana", "cherry")

assert isinstance(fruits_tuple, tuple)
assert fruits_tuple[0] == "apple"
assert fruits_tuple[1] == "banana"
assert fruits_tuple[2] == "cherry"
```

You cannot change values in a tuple.

```python
with pytest.raises(Exception):
    # pylint: disable=unsupported-assignment-operation
    fruits_tuple[0] = "pineapple"
```

It is also possible to use the `tuple()` constructor to make a tuple (note the double round-brackets).

The `len()` function returns the length of the tuple.

```python
fruits_tuple_via_constructor = tuple(("apple", "banana", "cherry"))

assert isinstance(fruits_tuple_via_constructor, tuple)
assert len(fruits_tuple_via_constructor) == 3
```

It is also possible to omit brackets when initializing tuples.

```python
another_tuple = 12345, 54321, 'hello!'
assert another_tuple == (12345, 54321, 'hello!')
```

Tuples may be nested:

```python
nested_tuple = another_tuple, (1, 2, 3, 4, 5)
assert nested_tuple == ((12345, 54321, 'hello!'), (1, 2, 3, 4, 5))
```

As you see, on output tuples are always enclosed in parentheses, so that nested tuples are interpreted correctly; they may be input with or without surrounding parentheses, although often parentheses are necessary anyway (if the tuple is part of a larger expression). It is not possible to assign to the individual items of a tuple, however, it is possible to create tuples that contain mutable objects, such as lists.

A special problem is the construction of tuples containing 0 or 1 item: the syntax has some extra quirks to accommodate these. Empty tuples are constructed by an empty pair of parentheses; a tuple with one item is constructed by following a value with a comma (it is not sufficient to enclose a single value in parentheses). Ugly, but effective. For example:

```python
empty_tuple = ()
# pylint: disable=len-as-condition
assert len(empty_tuple) == 0

# pylint: disable=trailing-comma-tuple
singleton_tuple = 'hello',  # <-- note trailing comma
assert len(singleton_tuple) == 1
assert singleton_tuple == ('hello',)
```

The following example is called **tuple packing**:

```python
packed_tuple = 12345, 54321, 'hello!'
```

The reverse operation is also possible.

```python
first_tuple_number, second_tuple_number, third_tuple_string = packed_tuple
assert first_tuple_number == 12345
assert second_tuple_number == 54321
assert third_tuple_string == 'hello!'
```

This is called, appropriately enough, **sequence unpacking** and works for any sequence on the right-hand side. Sequence unpacking requires that there are as many variables on the left side of the equals sign as there are elements in the sequence. 

Note that multiple assignments are really just a combination of tuple packing and sequence unpacking.

Data can be swapped from one variable to another in Python using tuples. This eliminates the need to use a 'temp' variable.

```python
first_number = 123
second_number = 456
first_number, second_number = second_number, first_number

assert first_number == 456
assert second_number == 123
```

[comment1]: <> (TODO: add visualization code example, e.g. some sample code from https://realpython.com/)

### Sets and their methods

A set is a collection that is unordered and unindexed.

In Python, sets are written with `{}`.

Set objects also support mathematical operations like union, intersection, difference, and symmetric difference.

```{seealso}
- https://www.w3schools.com/python/python_sets.asp
- https://docs.python.org/3.7/tutorial/datastructures.html#sets
```

#### Set type

```python
fruits_set = {"apple", "banana", "cherry"}

assert isinstance(fruits_set, set)
```

It is also possible to use the `set()` constructor to make a set. Note the `(())`.

```python
fruits_set_via_constructor = set(("apple", "banana", "cherry"))

assert isinstance(fruits_set_via_constructor, set)
```

#### Set methods

```python
fruits_set = {"apple", "banana", "cherry"}
```

You may check if the item is in set by using statement `in`.

```python
assert "apple" in fruits_set
assert "pineapple" not in fruits_set
```

Use the `len()` method to return the number of items.

```python
assert len(fruits_set) == 3
```

You can use the `add()` object method to add an item.

```python
fruits_set.add("pineapple")
assert "pineapple" in fruits_set
assert len(fruits_set) == 4
```

Use `remove()` object method to remove an item.

```python
fruits_set.remove("pineapple")
assert "pineapple" not in fruits_set
assert len(fruits_set) == 3
```

Demonstrate set operations on unique letters from two words:

```python
first_char_set = set('abracadabra')
second_char_set = set('alacazam')

assert first_char_set == {'a', 'r', 'b', 'c', 'd'}  # unique letters in first word
assert second_char_set == {'a', 'l', 'c', 'z', 'm'}  # unique letters in second word
```

Letters in the first word but not in second.

```python
assert first_char_set - second_char_set == {'r', 'b', 'd'}
```

Letters in the first word or second word or both.

```python
assert first_char_set | second_char_set == {'a', 'c', 'r', 'd', 'b', 'm', 'z', 'l'}
```

Common letters in both words.

```python
assert first_char_set & second_char_set == {'a', 'c'}
```

Letters in first or second word but not both.

```python
assert first_char_set ^ second_char_set == {'r', 'd', 'b', 'm', 'z', 'l'}
```

Similarly to list comprehensions, set comprehensions are also supported:

```python
word = {char for char in 'abracadabra' if char not in 'abc'}
assert word == {'r', 'd'}
```

#### Let's visualize it

Now you've seen some of the tools and techniques of `set`, so when you come across a bunch of data, you can use `set` to process them. Let’s look at some real-world examples.

##### Remove Duplicates from a List

Suppose you have a list, but there are some duplicate elements in it, and you want to get rid of these duplicates, you can use set to implement it.

```python
def remove_duplicates(lst):
    return list(set(lst))

numbers = [1, 2, 3, 3, 4, 5, 5, 6]
unique_numbers = remove_duplicates(numbers)
print(unique_numbers)
```

We can do it by converting a list into a set and then into a list, taking advantage of the fact that there are no duplicate elements in a set

##### Check if two strings are Anagrams:

When using set on an object of type string, we find that string is split into unordered letters, so we can use it to do some things.

```python
def are_anagrams(str1, str2):
    return set(str1) == set(str2)

word1 = "listen"
word2 = "silent"
if are_anagrams(word1, word2):
    print("The words are anagrams.")
else:
    print("The words are not anagrams.")
```

In this example, we use this feature of set to compare two words to see if they are Anagrams.

##### Find common elements in multiple lists:

When you want to ask for the intersection of some lists to find their common ground, you need set to help you.

```python
def find_common_elements(lists):
    common_elements = set(lists[0])
    for lst in lists[1:]:
        common_elements = common_elements.intersection(lst)
    return common_elements

lists = [[1, 2, 3, 4], [3, 4, 5, 6], [2, 4, 6, 8]]
common = find_common_elements(lists)
print(common)
```

The function of the intersection method is to find the intersection of the object and the argument, which has the same effect as using the & operation. But regardless of which method is used to find the intersection, the object must be set.

##### Count the number of Vowels in a string:

Similarly, we can put keywords in set to count the number of times they appear in the input.

```python
def count_vowels(string):
    vowels = {'a', 'e', 'i', 'o', 'u'}
    count = 0
    for char in string:
        if char.lower() in vowels:
            count += 1
    return count

sentence = "Hello, World!"
num_vowels = count_vowels(sentence)
print(num_vowels)
```

Although it appears that set can be replaced with list here, set supports fast member checking whereas list can only traverse members in a linear search. So when dealing with larger amounts of content, set is significantly better than list.

[comment2]: <> (TODO: add visualization code example, e.g. some sample code from https://realpython.com/)

### Dictionaries

A dictionary is a collection that is unordered, changeable and indexed. In Python, dictionaries are written with curly brackets, and they have keys and values.

Dictionaries are sometimes found in other languages as “associative memories” or “associative arrays”. Unlike sequences, which are indexed by a range of numbers, dictionaries are indexed by keys, which can be any immutable type; strings and numbers can always be keys. Tuples can be used as keys if they contain only strings, numbers, or tuples; if a tuple contains any mutable object either directly or indirectly, it cannot be used as a key. You can’t use lists as keys, since lists can be modified in place using index assignments, slice assignments, or methods like `append()` and `extend()`.

It is best to think of a dictionary as a set of key: value pairs, with the requirement that the keys are unique (within one dictionary). A pair of braces creates an empty dictionary: `{}`. Placing a comma-separated list of key-value pairs within the braces adds initial key-value pairs to the dictionary; this is also the way dictionaries are written on output.

```{seealso}
- https://docs.python.org/3/tutorial/datastructures.html#dictionaries
- https://www.w3schools.com/python/python_dictionaries.asp
```

```python
fruits_dictionary = {
    'cherry': 'red',
    'apple': 'green',
    'banana': 'yellow',
}

assert isinstance(fruits_dictionary, dict)
```

You may access set elements by keys.

```python
assert fruits_dictionary['apple'] == 'green'
assert fruits_dictionary['banana'] == 'yellow'
assert fruits_dictionary['cherry'] == 'red'
```

To check whether a single key is in the dictionary, use the keyword `in`.

```python
assert 'apple' in fruits_dictionary
assert 'pineapple' not in fruits_dictionary
```

Change the apple color to "red".

```python
fruits_dictionary['apple'] = 'red'
```

Add new key/value pair to the dictionary.

```python
fruits_dictionary['pineapple'] = 'yellow'
assert fruits_dictionary['pineapple'] == 'yellow'
```

Performing `list(d)` on a dictionary returns a list of all the keys used in the dictionary, in insertion order. (If you want it sorted, just use `sorted(d)` instead.)

```python
assert list(fruits_dictionary) == ['cherry', 'apple', 'banana', 'pineapple']
assert sorted(fruits_dictionary) == ['apple', 'banana', 'cherry', 'pineapple']
```

It is also possible to delete a key-value pair with `del`.

```python
del fruits_dictionary['pineapple']
assert list(fruits_dictionary) == ['cherry', 'apple', 'banana']
```

The `dict()` constructor builds dictionaries directly from sequences of key-value pairs.

```python
dictionary_via_constructor = dict([('sape', 4139), ('guido', 4127), ('jack', 4098)])

assert dictionary_via_constructor['sape'] == 4139
assert dictionary_via_constructor['guido'] == 4127
assert dictionary_via_constructor['jack'] == 4098
```

In addition, dict comprehensions can be used to create dictionaries from arbitrary key and value expressions:

```python
dictionary_via_expression = {x: x**2 for x in (2, 4, 6)}
assert dictionary_via_expression[2] == 4
assert dictionary_via_expression[4] == 16
assert dictionary_via_expression[6] == 36
```

When the keys are simple strings, it is sometimes easier to specify pairs using keyword arguments.

```python
dictionary_for_string_keys = dict(sape=4139, guido=4127, jack=4098)
assert dictionary_for_string_keys['sape'] == 4139
assert dictionary_for_string_keys['guido'] == 4127
assert dictionary_for_string_keys['jack'] == 4098
```

#### Let's visualize it

So far, you’ve seen the more basic ways of accessing through a dictionary in Python. Now it’s time to see how you can perform some actions with the items of a dictionary during iteration. Let’s look at some real-world examples.

```{seealso}
Note: Later on in this article, you’ll see another way of solving these very same problems by using other Python tools.
```

##### Turning keys into values and vice versa

Suppose you have a dictionary and for some reason need to turn keys into values and vice versa. In this situation, you can use a for loop to iterate through the dictionary and build the new dictionary by using the keys as values and vice versa:

```python
a_dict = {'one': 1, 'two': 2, 'thee': 3, 'four': 4}
new_dict = {}
for key, value in a_dict.items():
    new_dict[value] = key

new_dict
```

The expression new_dict[value] = key did all the work for you by turning the keys into values and using the values as keys. For this code to work, the data stored in the original values must be of a hashable data type.

##### Filtering Items
Sometimes you’ll be in situations where you have a dictionary and you want to create a new one to store only the data that satisfies a given condition. You can do this with an if statement inside a for loop as follows:

```python
a_dict = {'one': 1, 'two': 2, 'thee': 3, 'four': 4}
new_dict = {}  # Create a new empty dictionary
for key, value in a_dict.items():
    # If value satisfies the condition, then store it in new_dict
    if value <= 2:
        new_dict[key] = value

new_dict
```

In this example, you’ve filtered out the items with a value greater than 2. Now new_dict only contains the items that satisfy the condition value <= 2. This is one possible solution for this kind of problem. Later on, you’ll see a more Pythonic and readable way to get the same result.

##### Doing Some Calculations
It’s also common to need to do some calculations while you iterate through a dictionary in Python. Suppose you’ve stored the data for your company’s sales in a dictionary, and now you want to know the total income of the year.

To solve this problem you could define a variable with an initial value of zero. Then, you can accumulate every value of your dictionary in that variable:

```python
incomes = {'apple': 5600.00, 'orange': 3500.00, 'banana': 5000.00}
total_income = 0.00
for value in incomes.values():
    total_income += value  # Accumulate the values in total_income

total_income
```

Here, you’ve iterated through incomes and sequentially accumulated its values in total_income as you wanted to do. The expression total_income += value does the magic, and at the end of the loop, you’ll get the total income of the year. Note that total_income += value is equivalent to total_income = total_income + value.

### Type casting

There may be times when you want to specify a type to a variable. This can be done with **casting**. Python is an object-orientated language, and as such it uses classes to define data types, including its primitive types. Casting in Python is therefore done using constructor functions.

- `int()` - constructs an integer number from an integer literal, a float literal (by rounding down
to the previous whole number) literal, or a string literal (providing the string represents a
whole number)
- `float()` - constructs a float number from an integer literal, a float literal or a string literal
(providing the string represents a float or an integer)
- `str()` - constructs a string from a wide variety of data types, including strings, integer
literals and float literals

```{seealso}
- https://www.w3schools.com/python/python_casting.asp
```

Type casting to integer.

```python
assert int(1) == 1
assert int(2.8) == 2
assert int('3') == 3
```

Type casting to float.

```python
assert float(1) == 1.0
assert float(2.8) == 2.8
assert float("3") == 3.0
assert float("4.2") == 4.2
```

Type casting to string.

```python
assert str("s1") == 's1'
assert str(2) == '2'
assert str(3.0) == '3.0'
```

## Your turn! 🚀

Practice the Python programming basics by following this assignment（请通过本页“官方章节”链接查看）.

## Self study

Here is a list of free/open source learning resources for advanced [Python programming](https://github.com/ocademy-ai/open-learning-resources/blob/main/README.md#python).

## Acknowledgments

Thanks to [learn-python](https://github.com/trekhleb/learn-python) by [Oleksii Trekhleb](https://github.com/trekhleb) and [Real Python](https://realpython.com/). They contribute the majority of the content in this chapter.

---

> 编辑说明：本稿完成来源、许可证、文本结构、危险嵌入、知识点映射和部署可读性检查；学科正确性与教学难度仍应由课程负责人抽检后持续迭代。
