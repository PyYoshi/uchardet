#!/bin/python3
# -*- coding: utf-8 -*-

# ##### BEGIN LICENSE BLOCK #####
# Version: MPL 1.1/GPL 2.0/LGPL 2.1
#
# The contents of this file are subject to the Mozilla Public License Version
# 1.1 (the "License"); you may not use this file except in compliance with
# the License. You may obtain a copy of the License at
# http://www.mozilla.org/MPL/
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License
# for the specific language governing rights and limitations under the
# License.
#
# The Original Code is Mozilla Universal charset detector code.
#
# The Initial Developer of the Original Code is
# Netscape Communications Corporation.
# Portions created by the Initial Developer are Copyright (C) 2001
# the Initial Developer. All Rights Reserved.
#
# Contributor(s):
#          Jehan <jehan@girinstud.io>
#
# Alternatively, the contents of this file may be used under the terms of
# either the GNU General Public License Version 2 or later (the "GPL"), or
# the GNU Lesser General Public License Version 2.1 or later (the "LGPL"),
# in which case the provisions of the GPL or the LGPL are applicable instead
# of those above. If you wish to allow use of your version of this file only
# under the terms of either the GPL or the LGPL, and not to allow others to
# use your version of this file under the terms of the MPL, indicate your
# decision by deleting the provisions above and replace them with the notice
# and other provisions required by the GPL or the LGPL. If you do not delete
# the provisions above, a recipient may use your version of this file under
# the terms of any one of the MPL, the GPL or the LGPL.
#
# ##### END LICENSE BLOCK #####

# Third party modules.
import unicodedata
import subprocess
import wikipedia
import importlib
import math
import optparse
import datetime
import operator
import requests
import sys
import re
import os
import random

# Custom modules.
import charsets.db
from charsets.codepoints import *

# Command line processing.
usage = 'Usage: {} <LANG-CODE>\n' \
        '\nEx: `{} fr`'.format(__file__, __file__)

description = "Internal tool for uchardet to generate language data."
cmdline = optparse.OptionParser(usage, description = description)
cmdline.add_option('--max-page',
                   help = 'Maximum number of Wikipedia pages to parse (useful for debugging).',
                   action = 'store', type = 'int', dest = 'max_page', default = None)
cmdline.add_option('--max-depth',
                   help = 'Maximum depth when following links from start page (default: 2).',
                   action = 'store', type = 'int',
                   dest = 'max_depth', default = 2)
(options, langs) = cmdline.parse_args()
if len(langs) < 1:
  sys.stderr.write("Please select at least one language code. ")
  sys.stderr.write("You may also choose 'all' or 'none'.\n")
  exit(1)

current_dir = os.path.dirname(os.path.realpath(__file__))

with open(os.path.join(current_dir, "support.txt")) as f:
    all_langs = f.readlines()
all_langs = [ l.strip() for l in all_langs if l.strip() != '' ]

if len(langs) == 1:
  if langs[0].lower() == 'none':
    langs = []
  elif langs[0].lower() == 'all':
    langs = all_langs

abort = False
for lang in langs:
  if lang not in all_langs:
    abort = True
    sys.stderr.write("Error: unsupported lang: {}\n".format(lang))
if abort:
  sys.stderr.write("Info: new langs must be added in 'script/support.txt'.\n")
  exit(1)

generated_files = []

for lang_arg in langs:
  lang_arg = lang_arg.lower()

  # Load the language data.
  sys_path_backup = sys.path
  sys.path = [current_dir + '/langs']
  try:
      lang = importlib.import_module(lang_arg)
  except ImportError:
      sys.stderr.write('Unknown language code "{}": '
                       'file "langs/{}.py" does not exist.'.format(lang_arg, lang_arg))
      exit(1)
  sys.path = sys_path_backup

  print("Processing language data for {} (lang/{}.py):\n".format(lang_arg, lang_arg))

  lang_charsets = charsets.db.load(lang.charsets)

  if not hasattr(lang, 'start_pages') or lang.start_pages is None or \
     lang.start_pages == []:
      # Let's start with the main page, assuming it should have links
      # to relevant pages. In locale wikipedia, this page is usually redirected
      # to a relevant page.
      sys.stderr.write("Warning: no `start_pages` set for '{}'. Using ['Main_Page'].\n"
                       "         If you don't get good data, it is advised to set a "
                       "start_pages` variable yourself.".format(lang.code))
      lang.start_pages = ['Main_Page']
  if not hasattr(lang, 'wikipedia_code') or lang.wikipedia_code is None:
      lang.wikipedia_code = lang.code
  if not hasattr(lang, 'clean_wikipedia_content') or lang.clean_wikipedia_content is None:
      lang.clean_wikipedia_content = None
  if hasattr(lang, 'case_mapping'):
      lang.case_mapping = bool(lang.case_mapping)
  else:
      lang.case_mapping = False
  if not hasattr(lang, 'custom_case_mapping'):
      lang.custom_case_mapping = None
  if not hasattr(lang, 'alphabet') or lang.alphabet is None:
      lang.alphabet = None
  if not hasattr(lang, 'alphabet_mapping') or lang.alphabet_mapping is None:
      lang.alphabet_mapping = None
  if not hasattr(lang, 'unicode_ranges') or lang.unicode_ranges is None:
      lang.unicode_ranges = None
  if not hasattr(lang, 'frequent_ranges') or lang.frequent_ranges is None:
      if lang.unicode_ranges is not None:
        lang.frequent_ranges = lang.unicode_ranges
      else:
        lang.frequent_ranges = None

  def local_lowercase(text, lang):
      lowercased = ''
      for l in text:
          if lang.custom_case_mapping is not None and \
             l in lang.custom_case_mapping:
              lowercased += lang.custom_case_mapping[l]
          elif l.isupper() and \
               lang.case_mapping and \
               len(unicodedata.normalize('NFC', l.lower())) == 1:
              lowercased += l.lower()
          else:
              lowercased += l
      return lowercased

  if lang.use_ascii:
      if lang.alphabet is None:
          lang.alphabet = [chr(l) for l in range(65, 91)] + [chr(l) for l in range(97, 123)]
      else:
          # Allowing to provide an alphabet in string format rather than list.
          lang.alphabet = list(lang.alphabet)
          lang.alphabet += [chr(l) for l in range(65, 91)] + [chr(l) for l in range(97, 123)]
  if lang.alphabet is not None:
      # Allowing to provide an alphabet in string format rather than list.
      lang.alphabet = list(lang.alphabet)
      if lang.case_mapping or lang.custom_case_mapping is not None:
          lang.alphabet = [local_lowercase(l, lang) for l in lang.alphabet]
          #alphabet = []
          #for l in lang.alphabet:
              #if l.isupper() and \
                 #lang.custom_case_mapping is not None and \
                 #l in lang.custom_case_mapping:
                  #alphabet.append(lang.custom_case_mapping[l])
              #elif l.isupper() and \
                   #lang.case_mapping and \
                   #len(unicodedata.normalize('NFC', l.lower())) == 1:
                  #alphabet.append(l.lower())
              #else:
                  #alphabet.append(l)
      lang.alphabet = list(set(lang.alphabet))

  if lang.alphabet_mapping is not None:
      alphabet_mapping = {}
      for char in lang.alphabet_mapping:
        # Allowing to provide an alphabet in string format rather than list.
        for alt_char in list(lang.alphabet_mapping[char]):
          # While it's easier to write from main character to
          # equivalencies in the language file, we reverse the mapping
          # for simpler usage.
          if lang.case_mapping or lang.custom_case_mapping is not None:
            alphabet_mapping[alt_char] = local_lowercase(char, lang)
          else:
            alphabet_mapping[alt_char] = char
      lang.alphabet_mapping = alphabet_mapping

  def normalize_codepoint_ranges(input_range):
    output_range = []
    if input_range is not None:
        for start, end in input_range:
          # Allow to write down characters rather than unicode values.
          if isinstance(start, str):
            start = ord(start)
          if isinstance(end, str):
            end = ord(end)
          if not isinstance(start, int) or not isinstance(end, int):
            sys.stderr.write("Expected unicode range in char or int: {}-{}.\n".format(start, end))
          if start > end:
            sys.stderr.write("Wrong unicode range: {}-{}.\n".format(start, end))
          else:
            output_range += [(start, end)]
    if len(output_range) == 0:
      output_range = None
    return output_range

  lang.unicode_ranges = normalize_codepoint_ranges(lang.unicode_ranges)
  lang.frequent_ranges = normalize_codepoint_ranges(lang.frequent_ranges)

  # Starting processing.
  wikipedia.set_lang(lang.wikipedia_code)

  visited_pages = []

  # The full list of letter characters.
  # The key is the unicode codepoint,
  # and the value is the occurrence count.
  characters = {}
  # Sequence of letters.
  # The key is the couple (char1, char2) in unicode codepoint,
  # the value is the occurrence count.
  sequences = {}
  prev_char = None

  def process_text(content, lang):
      global lang_charsets
      global characters
      global sequences
      global prev_char

      if lang.clean_wikipedia_content is not None:
          content = lang.clean_wikipedia_content(content)
      # Clean out the Wikipedia syntax for titles.
      content = re.sub(r'(=+) *([^=]+) *\1',
                       r'\2', content)
      # Clean multiple spaces. Newlines and such are normalized to spaces,
      # since they have basically a similar role in the purpose of uchardet.
      content = re.sub(r'\s+', ' ', content)

      if lang.case_mapping or lang.custom_case_mapping is not None:
          content = local_lowercase(content, lang)

      # In python 3, strings are UTF-8.
      # Looping through them return expected characters.
      for char in content:
          # Map to main equivalent character.
          if lang.alphabet_mapping is not None and \
             char in lang.alphabet_mapping:
            char = lang.alphabet_mapping[char]

          unicode_value = ord(char)
          is_letter = False
          if unicode_value in characters:
              characters[unicode_value] += 1
              is_letter = True
          elif lang.unicode_ranges is not None:
              for start, end in lang.unicode_ranges:
                if unicode_value >= start and unicode_value <= end:
                  characters[unicode_value] = 1
                  is_letter = True
                  break
          else:
              # We save the character if it is at least in one of the
              # language encodings and its not a special character.
              for charset in lang_charsets:
                  # Does the character exist in the charset?
                  try:
                      codepoint = char.encode(charset, 'ignore')
                  except LookupError:
                      # unknown encoding. Use iconv from command line instead.
                      try:
                          call = subprocess.Popen(['iconv', '-f', 'UTF-8', '-t', charset],
                                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                                  stderr=subprocess.DEVNULL)
                          if call.poll() is not None:
                              (_, error) = call.communicate(input='')
                              sys.stderr.write('Error: `iconv` ended with error "{}".\n'.format(error))
                              exit(1)
                          (codepoint, _) = call.communicate(input=char.encode('UTF-8'))
                      except FileNotFoundError:
                          sys.stderr.write('Error: "{}" is not a supported charset by python and `iconv` is not installed.\n')
                          exit(1)

                  if codepoint == b'':
                      continue
                  # ord() is said to return the unicode codepoint.
                  # But it turns out it also gives the codepoint for other
                  # charsets if I turn the string to encoded bytes first.
                  # Not sure if that is a bug or expected.
                  codepoint = ord(codepoint)
                  if lang_charsets[charset].charmap[codepoint] == LET:
                      characters[unicode_value] = 1
                      is_letter = True
                      break
          if is_letter:
              if prev_char is not None:
                  if (prev_char, unicode_value) in sequences:
                      sequences[(prev_char, unicode_value)] += 1
                  else:
                      sequences[(prev_char, unicode_value)] = 1
              prev_char = unicode_value
          else:
              prev_char = None

  def visit_pages(titles, depth, lang, logfd):
      global visited_pages
      global options

      if len(titles) == 0:
          return

      next_titles = []
      if options.max_page is not None:
        max_titles = int(options.max_page/(options.max_depth * options.max_depth))
      else:
        max_titles = sys.maxsize
      for title in titles:
          if options.max_page is not None and \
             len(visited_pages) > options.max_page:
              return
          if title in visited_pages:
              continue

          # Ugly hack skipping internal pages
          if 'wiki' in title or 'Wiki' in title:
              sys.stderr.write('Skipping {}'.format(title))
              continue

          visited_pages += [title]
          try:
              page = wikipedia.page(title, auto_suggest=False)
          except (wikipedia.exceptions.PageError,
                  wikipedia.exceptions.DisambiguationError) as error:
              # Let's just discard a page when I get an exception.
              sys.stderr.write("Discarding page {}: {}\n".format(title, error))
              continue
          logfd.write("\n{} (revision {})".format(title, page.revision_id))
          logfd.flush()

          process_text(page.content, lang)
          try:
            links = page.links
            random.shuffle(links)
            if len(links) > max_titles:
                links = links[:max_titles]
                next_titles += links
          except KeyError:
              pass

      if depth >= options.max_depth:
          return

      random.shuffle(next_titles)
      visit_pages (next_titles, depth + 1, lang, logfd)

  language_c = lang.name.replace('-', '_').title()
  build_log = current_dir + '/BuildLangModelLogs/Lang{}Model.log'.format(language_c)
  logfd = open(build_log, 'w')
  logfd.write('= Logs of language model for {} ({}) =\n'.format(lang.name, lang.code))
  logfd.write('\n- Generated by {}'.format(os.path.basename(__file__)))
  logfd.write('\n- Started: {}'.format(str(datetime.datetime.now())))
  logfd.write('\n- Maximum depth: {}'.format(options.max_depth))
  if options.max_page is not None:
      logfd.write('\n- Max number of pages: {}'.format(options.max_page))
  logfd.write('\n\n== Parsed pages ==\n')
  logfd.flush()
  try:
      visit_pages(lang.start_pages, 0, lang, logfd)
  except requests.exceptions.ConnectionError:
      sys.stderr.write('Error: connection to Wikipedia failed. Aborting\n')
      exit(1)
  logfd.write('\n\n== End of Parsed pages ==')
  logfd.write('\n\n- Wikipedia parsing ended at: {}\n'.format(str(datetime.datetime.now())))
  logfd.flush()

  ########### CHARACTERS ###########

  # Character ratios.
  ratios = {}
  n_char = len(characters)
  occurrences = sum(characters.values())

  logfd.write("\n{} characters appeared {} times.\n".format(n_char, occurrences))
  for char in characters:
      ratios[char] = characters[char] / occurrences
      #logfd.write("Character '{}' usage: {} ({} %)\n".format(chr(char),
      #                                                       characters[char],
      #                                                       ratios[char] * 100))

  sorted_ratios = sorted(ratios.items(), key=operator.itemgetter(1),
                         reverse=True)
  # Accumulated ratios of the frequent chars.
  accumulated_ratios = 0

  # If there is no alphabet defined, we just use the first 64 letters, which was
  # the original default.
  # If there is an alphabet, we make sure all the alphabet characters are in the
  # frequent list, and we stop then. There may therefore be more or less than
  # 64 frequent characters depending on the language.
  logfd.write('\nMost Frequent characters:')
  very_freq_count = 0
  very_freq_ratio = 0
  if lang.alphabet is None and lang.frequent_ranges is None:
      freq_count = min(64, len(sorted_ratios))
      for order, (char, ratio) in enumerate(sorted_ratios):
          if order >= freq_count:
              break
          logfd.write("\n[{:2}] Char {}: {} %".format(order, chr(char), ratio * 100))
          accumulated_ratios += ratio
          if very_freq_ratio < 0.4:
            very_freq_count += 1
            very_freq_ratio += ratio
  elif lang.alphabet is not None:
      freq_count = 0
      for order, (char, ratio) in enumerate(sorted_ratios):
          if len(lang.alphabet) == 0:
              break
          if chr(char) in lang.alphabet:
              lang.alphabet.remove(chr(char))
          logfd.write("\n[{:2}] Char {}: {} %".format(order, chr(char), ratio * 100))
          accumulated_ratios += ratio
          freq_count += 1
          if very_freq_ratio < 0.4:
            very_freq_count += 1
            very_freq_ratio += ratio
      else:
          if len(lang.alphabet) > 0:
              sys.stderr.write("Error: alphabet characters are absent from data collection"
                               "\n       Please check the configuration or the data."
                               "\n       Missing characters: {}".format(", ".join(lang.alphabet)))
              exit(1)
  elif lang.frequent_ranges is not None:
      # How many characters in the frequent range?
      frequent_ranges_size = 0
      for start, end in lang.frequent_ranges:
        frequent_ranges_size += end - start + 1

      # Keep ratio for at least all the characters inside the frequent
      # ranges.
      freq_count = 0
      for order, (char, ratio) in enumerate(sorted_ratios):
        for start, end in lang.frequent_ranges:
          if char >= start and char <= end:
            freq_count += 1
            accumulated_ratios += ratio
            logfd.write("\n[{:2}] Char {}: {} %".format(order, chr(char), ratio * 100))
            frequent_ranges_size -= 1
            break
        else:
          # A frequent character in the non-frequent range.
          logfd.write("\n[{:2}] Char {}: {} %".format(order, chr(char), ratio * 100))
          freq_count += 1
          accumulated_ratios += ratio

        if very_freq_ratio < 0.4:
          very_freq_count += 1
          very_freq_ratio += ratio

        if frequent_ranges_size <= 0:
          break

  low_freq_order = freq_count - 1
  low_freq_ratio = 0
  for back_order, (char, ratio) in enumerate(reversed(sorted_ratios[:freq_count])):
    if low_freq_ratio < 0.03:
      low_freq_ratio += ratio
      low_freq_order -= 1
    else:
      break

  logfd.write("\n\nThe first {} characters have an accumulated ratio of {}.\n".format(freq_count, accumulated_ratios))
  logfd.write("The first {} characters have an accumulated ratio of {}.\n".format(very_freq_count, very_freq_ratio))
  logfd.write("All characters whose order is over {} have an accumulated ratio of {}.\n".format(low_freq_order, low_freq_ratio))

  with open(current_dir + '/header-template.cpp', 'r') as header_fd:
      c_code = header_fd.read()

  c_code += '\n#include "../nsSBCharSetProber.h"'
  c_code += '\n#include "../nsSBCharSetProber-generated.h"'
  c_code += '\n#include "../nsLanguageDetector.h"\n'
  c_code += '\n#include "../nsLanguageDetector-generated.h"\n'
  c_code += '\n/********* Language model for: {} *********/\n\n'.format(lang.name)
  c_code += '/**\n * Generated by {}\n'.format(os.path.basename(__file__))
  c_code += ' * On: {}\n'.format(str(datetime.datetime.now()))
  c_code += ' **/\n'

  c_code += \
  """
  /* Character Mapping Table:
   * ILL: illegal character.
   * CTR: control character specific to the charset.
   * RET: carriage/return.
   * SYM: symbol (punctuation) that does not belong to word.
   * NUM: 0 - 9.
   *
   * Other characters are ordered by probabilities
   * (0 is the most common character in the language).
   *
   * Orders are generic to a language. So the codepoint with order X in
   * CHARSET1 maps to the same character as the codepoint with the same
   * order X in CHARSET2 for the same language.
   * As such, it is possible to get missing order. For instance the
   * ligature of 'o' and 'e' exists in ISO-8859-15 but not in ISO-8859-1
   * even though they are both used for French. Same for the euro sign.
   */
  """

  for charset in lang_charsets:
      charset_c = charset.replace('-', '_').title()
      CTOM_str = 'static const unsigned char {}_CharToOrderMap[]'.format(charset_c)
      CTOM_str += ' =\n{'
      for line in range(0, 16):
          CTOM_str += '\n  '
          for column in range(0, 16):
              cp = line * 16 + column
              cp_type = lang_charsets[charset].charmap[cp]
              if cp_type == ILL:
                  CTOM_str += 'ILL,'
              elif cp_type == RET:
                  CTOM_str += 'RET,'
              elif cp_type == CTR:
                  CTOM_str += 'CTR,'
              elif cp_type == SYM:
                  CTOM_str += 'SYM,'
              elif cp_type == NUM:
                  CTOM_str += 'NUM,'
              else: # LET
                  try:
                      uchar = bytes([cp]).decode(charset)
                  except UnicodeDecodeError:
                      sys.stderr.write('Unknown character 0X{:X} in {}.'.format(cp, charset))
                      sys.stderr.write('Please verify your charset specification.\n')
                      exit(1)
                  except LookupError:
                      # Unknown encoding. Use iconv instead.
                      try:
                          call = subprocess.Popen(['iconv', '-t', 'UTF-8', '-f', charset],
                                                  stdin=subprocess.PIPE,
                                                  stdout=subprocess.PIPE,
                                                  stderr=subprocess.PIPE)
                          if call.poll() is not None:
                              (_, error) = call.communicate(input='')
                              sys.stderr.write('Error: `iconv` ended with error "{}".\n'.format(error))
                              exit(1)
                          (uchar, _) = call.communicate(input=bytes([cp]))
                          uchar = uchar.decode('UTF-8')
                      except FileNotFoundError:
                          sys.stderr.write('Error: "{}" is not a supported charset by python and `iconv` is not installed.\n')
                          exit(1)
                      if len(uchar) == 0:
                          sys.stderr.write('TypeError: iconv failed to return a unicode character for codepoint "{}" in charset {}.\n'.format(hex(cp), charset))
                          exit(1)
                  #if lang.case_mapping and uchar.isupper() and \
                     #len(unicodedata.normalize('NFC', uchar.lower())) == 1:
                     # Unless we encounter special cases of characters with no
                     # composed lowercase, we lowercase it.
                  if lang.case_mapping or lang.custom_case_mapping is not None:
                      uchar = local_lowercase(uchar, lang)
                  if lang.alphabet_mapping is not None and uchar in lang.alphabet_mapping:
                      uchar = lang.alphabet_mapping[uchar]
                  for order, (char, ratio) in enumerate(sorted_ratios):
                      if char == ord(uchar):
                          CTOM_str += '{:3},'.format(min(249, order))
                          break
                  else:
                      # XXX: we must make sure the character order does not go
                      # over the special characters (250 currently). This may
                      # actually happen when building a model for a language
                      # writable with many different encoding. So let's just
                      # ceil the order value at 249 max.
                      # It may be an interesting alternative to add another
                      # constant for any character with an order > freqCharCount.
                      # Maybe IRR (irrelevant character) or simply CHR.
                      CTOM_str += '{:3},'.format(min(249, n_char))
                      n_char += 1
          CTOM_str += ' /* {:X}X */'.format(line)
      CTOM_str += '\n};\n/*'
      CTOM_str += 'X0  X1  X2  X3  X4  X5  X6  X7  X8  X9  XA  XB  XC  XD  XE  XF'
      CTOM_str += ' */\n\n'
      c_code += CTOM_str

  ## UNICODE frequency.

  # Since we can't map the full character table from encoding to order,
  # just create a list from the most common characters from the language.
  # The list is ordered by unicode code points (hence can be used
  # generically for various encoding scheme as it is not encoding
  # specific) allowing to search from code points efficiently by a divide
  # and conqueer search algorithm.
  # Each code point is immediately followed by its order.

  # Keep the freq_count more frequent characters.
  sorted_chars = [(char, freq, order) for order, (char, freq) in
                  enumerate(sorted_ratios)][:freq_count]
  max_order = len(sorted_chars)

  # Add equivalency characters.
  equivalent = []
  if lang.case_mapping:
      for char, ratio, order in sorted_chars:
          uppercased = chr(char).upper()
          try:
            if char != ord(uppercased):
                equivalent += [(ord(uppercased), ratio, order)]
          except TypeError:
            # This happens for some case such as 'SS' as uppercase of 'ß'.
            # Just ignore such cases.
            sys.stderr.write("Ignoring '{}' as uppercase equivalent of '{}'.\n".format(uppercased, char))

  if lang.alphabet_mapping is not None:
    for alt_c in lang.alphabet_mapping:
      for char, ratio, order in sorted_chars:
        if alt_c == chr(char):
          sys.stderr.write("ALREADY {}\n".format(alt_c))
          exit(1)
        elif char == ord(lang.alphabet_mapping[alt_c]):
          equivalent += [(ord(alt_c), ratio, order)]
          break
      else:
        sys.stderr.write("Base equivalent for {} not found in frequent characters!\n".format(alt_c))
        exit(1)

  sorted_chars += equivalent

  # Order by code point.
  sorted_chars = sorted(sorted_chars, key=operator.itemgetter(0))

  CTOM_str = 'static const int Unicode_Char_size = {};\n'.format(len(sorted_chars))

  CTOM_str += 'static const unsigned int Unicode_CharOrder[]'
  CTOM_str += ' =\n{'
  column = 0

  max_char_width  = math.floor(math.log10(sorted_chars[-1][0])) + 1
  max_order_width = math.floor(math.log10(max_order)) + 1

  for char, ratio, order in sorted_chars:
      if column % 8 == 0:
          CTOM_str += '\n '
      column += 1
      CTOM_str += '{}{:>{width}}, '.format('' if column % 8 == 0 else ' ', char, width=max_char_width)
      CTOM_str += '{:>{width}},'.format(order, width=max_order_width)

  CTOM_str += '\n};\n\n'
  c_code += CTOM_str

  ########### SEQUENCES ###########

  ratios = {}
  occurrences = sum(sequences.values())

  accumulated_seq_count = 0
  order_3 = -1
  order_2 = -1
  ratio_3 = -1
  ratio_2 = -1
  count_512 = -1
  count_1024 = -1
  sorted_seqs = sorted(sequences.items(), key=operator.itemgetter(1),
                       reverse=True)
  for order, ((c1, c2), count) in enumerate(sorted_seqs):
    accumulated_seq_count += count
    if order_3 == -1 and accumulated_seq_count / occurrences >= 0.995:
      order_3 = order
      ratio_3 = accumulated_seq_count / occurrences
    elif order_2 == -1 and accumulated_seq_count / occurrences >= 0.999:
      order_2 = order
      ratio_2 = accumulated_seq_count / occurrences
    if order < 512:
      count_512 += count
    elif order < 1024:
      count_1024 += count

    if order_3 != -1 and order_2 != -1:
      break

  if order_3 == -1 or order_2 == -1:
    # This would probably never happens. It would require a language with
    # very few possible sequences and each of the sequences are widely
    # used. Just add this code for completio, but it won't likely ever be
    # run.
    order_2 = 512
    order_3 = 1024
    ratio_2 = count_512 / occurrences
    ratio_3 = count_1024 / occurrences

  logfd.write("\n{} sequences found.\n".format(len(sorted_seqs)))

  c_code += """
  /* Model Table:
   * Total considered sequences: {} / {}
   * - Positive sequences: first {} ({})
   * - Probable sequences: next {} ({}-{}) ({})
   * - Neutral sequences: last {} ({})
   * - Negative sequences: {} (off-ratio)
   * Negative sequences: TODO""".format(len(sorted_seqs),
                                        freq_count * freq_count,
                                        order_3, ratio_3,
                                        order_2 - order_3,
                                        order_2, order_3,
                                        ratio_2 - ratio_3,
                                        freq_count * freq_count - order_2,
                                        1 - ratio_2,
                                        freq_count * freq_count - len(sorted_seqs))

  logfd.write("\nFirst {} (typical positive ratio): {}".format(order_3, ratio_3))
  logfd.write("\nNext {} ({}-{}): {}".format(order_2 - order_3,
                                             order_2, order_3,
                                             ratio_2 - ratio_3))
  logfd.write("\nRest: {}".format(1 - ratio_2))

  c_code += "\n */\n"

  LM_str = 'static const PRUint8 {}LangModel[]'.format(language_c)
  LM_str += ' =\n{'
  for line in range(0, freq_count):
      LM_str += '\n  '
      for column in range(0, freq_count):
          # Let's not make too long lines.
          if freq_count > 40 and column == int(freq_count / 2):
              LM_str += '\n   '
          first_order = int(line)
          second_order = column
          if first_order < len(sorted_ratios) and second_order < len(sorted_ratios):
              (first_char, _) = sorted_ratios[first_order]
              (second_char, _) = sorted_ratios[second_order]
              if (first_char, second_char) in sequences:
                  for order, (seq, _) in enumerate(sorted_seqs):
                      if seq == (first_char, second_char):
                          if order < order_3:
                              LM_str += '3,'
                          elif order < order_2:
                              LM_str += '2,'
                          else:
                              LM_str += '1,'
                          break
                  else:
                      pass # impossible!
                      LM_str += '0,'
              else:
                  LM_str += '0,'
          else:
              # It may indeed happen that we find less than 64 letters used for a
              # given language.
              LM_str += '0,'
  LM_str += '\n};\n'
  c_code += LM_str

  for charset in lang_charsets:
      charset_c = charset.replace('-', '_').title()
      SM_str = '\n\nconst SequenceModel {}{}Model ='.format(charset_c, language_c)
      SM_str += '\n{\n  '
      SM_str += '{}_CharToOrderMap,\n  {}LangModel,'.format(charset_c, language_c)
      SM_str += '\n  {},'.format(freq_count)
      SM_str += '\n  (float){},'.format(ratio_2)
      SM_str += '\n  {},'.format('PR_TRUE' if lang.use_ascii else 'PR_FALSE')
      SM_str += '\n  "{}",'.format(charset)
      SM_str += '\n  "{}"'.format(lang.code)
      SM_str += '\n};'
      c_code += SM_str

  SM_str = '\n\nconst LanguageModel {}Model ='.format(language_c)
  SM_str += '\n{'
  SM_str += '\n  "{}",'.format(lang.code)
  SM_str += '\n  Unicode_CharOrder,'
  SM_str += '\n  {},'.format(len(sorted_chars)) # Order is wrong!
  SM_str += '\n  {}LangModel,'.format(language_c)
  SM_str += '\n  {},'.format(freq_count)
  SM_str += '\n  {},'.format(very_freq_count)
  SM_str += '\n  (float){},'.format(very_freq_ratio)
  SM_str += '\n  {},'.format(low_freq_order)
  SM_str += '\n  (float){},'.format(low_freq_ratio)
  SM_str += '\n};'
  c_code += SM_str

  c_code += '\n'

  lang_model_file = current_dir + '/../src/LangModels/Lang{}Model.cpp'.format(language_c)
  with open(lang_model_file, 'w') as cpp_fd:
      cpp_fd.write(c_code)

  logfd.write('\n\n- Processing end: {}\n'.format(str(datetime.datetime.now())))
  logfd.close()

  generated_files += [ (lang_model_file, build_log) ]

charset_cpp = os.path.join(current_dir, '../src', 'nsSBCharSetProber-generated.h')
print("\nGenerating {}…".format(charset_cpp))

with open(charset_cpp, 'w') as cpp_fd:
  with open(current_dir + '/header-template.cpp', 'r') as header_fd:
    cpp_fd.write(header_fd.read())

  cpp_fd.write('\n#ifndef nsSingleByteCharSetProber_generated_h__')
  cpp_fd.write('\n#define nsSingleByteCharSetProber_generated_h__\n')

  all_extern_declarations = ''
  n_sequence_models = 0
  for l in all_langs:
    l = l.lower()
    # Load the language data.
    sys_path_backup = sys.path
    sys.path = [current_dir + '/langs']
    try:
        lang = importlib.import_module(l)
    except ImportError:
        sys.stderr.write('Unknown language code "{}": '
                         'file "langs/{}.py" does not exist.'.format(l, l))
        exit(1)
    sys.path = sys_path_backup

    language_c = lang.name.replace('-', '_').title()
    lang_charsets = charsets.db.load(lang.charsets)
    for charset in lang_charsets:
      charset_c = charset.replace('-', '_').title()
      all_extern_declarations += '\nextern const SequenceModel {}{}Model;'.format(charset_c, language_c)
      n_sequence_models += 1
    all_extern_declarations += '\n'

  cpp_fd.write('\n#define NUM_OF_SEQUENCE_MODELS {}\n'.format(n_sequence_models))
  cpp_fd.write('{}'.format(all_extern_declarations))
  cpp_fd.write('\n#endif /* nsSingleByteCharSetProber_generated_h__ */')

print("Done!")

language_cpp = os.path.join(current_dir, '../src', 'nsLanguageDetector-generated.h')
print("\nGenerating {}…".format(language_cpp))

with open(language_cpp, 'w') as cpp_fd:
  with open(current_dir + '/header-template.cpp', 'r') as header_fd:
    cpp_fd.write(header_fd.read())

  cpp_fd.write('\n#ifndef nsLanguageDetector_h_generated_h__')
  cpp_fd.write('\n#define nsLanguageDetector_h_generated_h__\n')

  all_extern_declarations = ''
  n_language_models = 0
  for l in all_langs:
    l = l.lower()
    # Load the language data.
    sys_path_backup = sys.path
    sys.path = [current_dir + '/langs']
    try:
        lang = importlib.import_module(l)
    except ImportError:
        sys.stderr.write('Unknown language code "{}": '
                         'file "langs/{}.py" does not exist.'.format(l, l))
        exit(1)
    sys.path = sys_path_backup

    language_c = lang.name.replace('-', '_').title()
    all_extern_declarations += '\nextern const LanguageModel {}Model;'.format(language_c)
    n_language_models += 1

  cpp_fd.write('\n#define NUM_OF_LANGUAGE_MODELS {}\n'.format(n_language_models))
  cpp_fd.write('{}'.format(all_extern_declarations))
  cpp_fd.write('\n\n#endif /* nsLanguageDetector_h_generated_h__ */')

print("Done!")
if len(generated_files) > 0:
  print("\nThe following language files has been generated:")
  for (lang_model_file, build_log) in generated_files:
    print("\n- Language file: {}".format(lang_model_file))
    print("\n  Build log: {}".format(build_log))

print("\nTODO:")
print("- edit nsSBCSGroupProber::nsSBCSGroupProber() in src/nsSBCSGroupProber.cpp manually to test new sequence models;")
print("- edit nsMBCSGroupProber::nsMBCSGroupProber() in src/nsMBCSGroupProber.cpp manually to test new language models;")
print("- add any new language files to src/CMakeLists.txt;")
print("- commit generated files if tests are successful.")
