/* -*- Mode: C++; tab-width: 2; indent-tabs-mode: nil; c-basic-offset: 2 -*- */
/* ***** BEGIN LICENSE BLOCK *****
 * Version: MPL 1.1/GPL 2.0/LGPL 2.1
 *
 * The contents of this file are subject to the Mozilla Public License Version
 * 1.1 (the "License"); you may not use this file except in compliance with
 * the License. You may obtain a copy of the License at
 * http://www.mozilla.org/MPL/
 *
 * Software distributed under the License is distributed on an "AS IS" basis,
 * WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License
 * for the specific language governing rights and limitations under the
 * License.
 *
 * The Original Code is Mozilla Communicator client code.
 *
 * The Initial Developer of the Original Code is
 * Netscape Communications Corporation.
 * Portions created by the Initial Developer are Copyright (C) 1998
 * the Initial Developer. All Rights Reserved.
 *
 * Contributor(s):
 *
 * Alternatively, the contents of this file may be used under the terms of
 * either the GNU General Public License Version 2 or later (the "GPL"), or
 * the GNU Lesser General Public License Version 2.1 or later (the "LGPL"),
 * in which case the provisions of the GPL or the LGPL are applicable instead
 * of those above. If you wish to allow use of your version of this file only
 * under the terms of either the GPL or the LGPL, and not to allow others to
 * use your version of this file under the terms of the MPL, indicate your
 * decision by deleting the provisions above and replace them with the notice
 * and other provisions required by the GPL or the LGPL. If you do not delete
 * the provisions above, a recipient may use your version of this file under
 * the terms of any one of the MPL, the GPL or the LGPL.
 *
 * ***** END LICENSE BLOCK ***** */

#include "../nsSBCharSetProber.h"

/********* Language model for: Slovene *********/

/**
 * Generated by BuildLangModel.py
 * On: 2017-03-27 20:00:03.239594
 **/

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
static const unsigned char Iso_8859_2_CharToOrderMap[] =
{
  CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,RET,CTR,CTR,RET,CTR,CTR, /* 0X */
  CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR, /* 1X */
  SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM, /* 2X */
  NUM,NUM,NUM,NUM,NUM,NUM,NUM,NUM,NUM,NUM,SYM,SYM,SYM,SYM,SYM,SYM, /* 3X */
  SYM,  0, 18, 19, 13,  1, 24, 17, 20,  2,  9, 11,  8, 14,  4,  3, /* 4X */
   12, 28,  5,  7,  6, 16, 10, 26, 27, 25, 15,SYM,SYM,SYM,SYM,SYM, /* 5X */
  SYM,  0, 18, 19, 13,  1, 24, 17, 20,  2,  9, 11,  8, 14,  4,  3, /* 6X */
   12, 28,  5,  7,  6, 16, 10, 26, 27, 25, 15,SYM,SYM,SYM,SYM,CTR, /* 7X */
  CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR, /* 8X */
  CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR, /* 9X */
  SYM, 42,SYM, 43,SYM, 44, 45,SYM,SYM, 22, 46, 47, 48,SYM, 23, 49, /* AX */
  SYM, 50,SYM, 51,SYM, 52, 53,SYM,SYM, 22, 54, 55, 56,SYM, 23, 57, /* BX */
   58, 32, 59, 60, 61, 62, 40, 34, 21, 29, 63, 37, 64, 30, 65, 66, /* CX */
   67, 68, 69, 31, 35, 70, 71,SYM, 72, 73, 39, 74, 36, 41, 75, 76, /* DX */
   77, 32, 78, 79, 80, 81, 40, 34, 21, 29, 82, 37, 83, 30, 84, 85, /* EX */
   86, 87, 88, 31, 35, 89, 90,SYM, 91, 92, 39, 93, 36, 41, 94,SYM, /* FX */
};
/*X0  X1  X2  X3  X4  X5  X6  X7  X8  X9  XA  XB  XC  XD  XE  XF */

static const unsigned char Iso_8859_16_CharToOrderMap[] =
{
  CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,RET,CTR,CTR,RET,CTR,CTR, /* 0X */
  CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR, /* 1X */
  SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM, /* 2X */
  NUM,NUM,NUM,NUM,NUM,NUM,NUM,NUM,NUM,NUM,SYM,SYM,SYM,SYM,SYM,SYM, /* 3X */
  SYM,  0, 18, 19, 13,  1, 24, 17, 20,  2,  9, 11,  8, 14,  4,  3, /* 4X */
   12, 28,  5,  7,  6, 16, 10, 26, 27, 25, 15,SYM,SYM,SYM,SYM,SYM, /* 5X */
  SYM,  0, 18, 19, 13,  1, 24, 17, 20,  2,  9, 11,  8, 14,  4,  3, /* 6X */
   12, 28,  5,  7,  6, 16, 10, 26, 27, 25, 15,SYM,SYM,SYM,SYM,CTR, /* 7X */
  CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR, /* 8X */
  CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR, /* 9X */
  SYM, 95, 96, 97,SYM,SYM, 22,SYM, 22,SYM, 98,SYM, 99,SYM,100,101, /* AX */
  SYM,SYM, 21,102, 23,SYM,SYM,SYM, 23, 21,103,SYM,104,105,106,107, /* BX */
  108, 32,109,110,111, 40,112, 34,113, 29, 33, 37,114, 30,115,116, /* CX */
  117,118,119, 31, 35,120,121,122,123,124, 39,125, 36,126,127,128, /* DX */
  129, 32,130,131,132, 40,133, 34,134, 29, 33, 37,135, 30,136,137, /* EX */
  138,139,140, 31, 35,141,142,143,144,145, 39,146, 36,147,148,149, /* FX */
};
/*X0  X1  X2  X3  X4  X5  X6  X7  X8  X9  XA  XB  XC  XD  XE  XF */

static const unsigned char Windows_1250_CharToOrderMap[] =
{
  CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,RET,CTR,CTR,RET,CTR,CTR, /* 0X */
  CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR, /* 1X */
  SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM, /* 2X */
  NUM,NUM,NUM,NUM,NUM,NUM,NUM,NUM,NUM,NUM,SYM,SYM,SYM,SYM,SYM,SYM, /* 3X */
  SYM,  0, 18, 19, 13,  1, 24, 17, 20,  2,  9, 11,  8, 14,  4,  3, /* 4X */
   12, 28,  5,  7,  6, 16, 10, 26, 27, 25, 15,SYM,SYM,SYM,SYM,SYM, /* 5X */
  SYM,  0, 18, 19, 13,  1, 24, 17, 20,  2,  9, 11,  8, 14,  4,  3, /* 6X */
   12, 28,  5,  7,  6, 16, 10, 26, 27, 25, 15,SYM,SYM,SYM,SYM,CTR, /* 7X */
  SYM,ILL,SYM,ILL,SYM,SYM,SYM,SYM,ILL,SYM, 22,SYM,150,151, 23,152, /* 8X */
  ILL,SYM,SYM,SYM,SYM,SYM,SYM,SYM,ILL,SYM, 22,SYM,153,154, 23,155, /* 9X */
  SYM,SYM,SYM,156,SYM,157,SYM,SYM,SYM,SYM,158,SYM,SYM,SYM,SYM,159, /* AX */
  SYM,SYM,SYM,160,SYM,SYM,SYM,SYM,SYM,161,162,SYM,163,SYM,164,165, /* BX */
  166, 32,167,168,169,170, 40, 34, 21, 29,171, 37,172, 30,173,174, /* CX */
  175,176,177, 31, 35,178,179,SYM,180,181, 39,182, 36, 41,183,184, /* DX */
  185, 32,186,187,188,189, 40, 34, 21, 29,190, 37,191, 30,192,193, /* EX */
  194,195,196, 31, 35,197,198,SYM,199,200, 39,201, 36, 41,202,SYM, /* FX */
};
/*X0  X1  X2  X3  X4  X5  X6  X7  X8  X9  XA  XB  XC  XD  XE  XF */

static const unsigned char Ibm852_CharToOrderMap[] =
{
  CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,RET,CTR,CTR,RET,CTR,CTR, /* 0X */
  CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR, /* 1X */
  SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM, /* 2X */
  NUM,NUM,NUM,NUM,NUM,NUM,NUM,NUM,NUM,NUM,SYM,SYM,SYM,SYM,SYM,SYM, /* 3X */
  SYM,  0, 18, 19, 13,  1, 24, 17, 20,  2,  9, 11,  8, 14,  4,  3, /* 4X */
   12, 28,  5,  7,  6, 16, 10, 26, 27, 25, 15,SYM,SYM,SYM,SYM,SYM, /* 5X */
  SYM,  0, 18, 19, 13,  1, 24, 17, 20,  2,  9, 11,  8, 14,  4,  3, /* 6X */
   12, 28,  5,  7,  6, 16, 10, 26, 27, 25, 15,SYM,SYM,SYM,SYM,CTR, /* 7X */
   34, 36, 29,203,204,205, 40, 34,206, 37,207,208,209,210,211, 40, /* 8X */
   29,212,213, 35,214,215,216,217,218,219, 36,220,221,222,SYM, 21, /* 9X */
   32, 30, 31, 39,223,224, 23, 23,225,226,SYM,227, 21,228,SYM,SYM, /* AX */
  SYM,SYM,SYM,SYM,SYM, 32,229,230,231,SYM,SYM,SYM,SYM,232,233,SYM, /* BX */
  SYM,SYM,SYM,SYM,SYM,SYM,234,235,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM, /* CX */
  236,237,238, 37,239,240, 30,241,242,SYM,SYM,SYM,SYM,243,244,SYM, /* DX */
   31,245, 35,246,247,248, 22, 22,249, 39,249,249, 41, 41,249,SYM, /* EX */
  SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,249,249,249,SYM,SYM, /* FX */
};
/*X0  X1  X2  X3  X4  X5  X6  X7  X8  X9  XA  XB  XC  XD  XE  XF */

static const unsigned char Maccentraleurope_CharToOrderMap[] =
{
  CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,RET,CTR,CTR,RET,CTR,CTR, /* 0X */
  CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR,CTR, /* 1X */
  SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM, /* 2X */
  NUM,NUM,NUM,NUM,NUM,NUM,NUM,NUM,NUM,NUM,SYM,SYM,SYM,SYM,SYM,SYM, /* 3X */
  SYM,  0, 18, 19, 13,  1, 24, 17, 20,  2,  9, 11,  8, 14,  4,  3, /* 4X */
   12, 28,  5,  7,  6, 16, 10, 26, 27, 25, 15,SYM,SYM,SYM,SYM,SYM, /* 5X */
  SYM,  0, 18, 19, 13,  1, 24, 17, 20,  2,  9, 11,  8, 14,  4,  3, /* 6X */
   12, 28,  5,  7,  6, 16, 10, 26, 27, 25, 15,SYM,SYM,SYM,SYM,CTR, /* 7X */
  249,249,249, 29,249,249, 36, 32,249, 21,249, 21, 40, 40, 29,249, /* 8X */
  249,249, 30,249, 38, 38,249, 31,249, 35,249,249, 39,249,249, 36, /* 9X */
  SYM,SYM,249,SYM,SYM,SYM,SYM,249,SYM,SYM,SYM,249,SYM,SYM,249,249, /* AX */
  249,249,SYM,SYM,249,249,SYM,SYM,249,249,249,249,249,249,249,249, /* BX */
  249,249,SYM,SYM,249,249,SYM,SYM,SYM,SYM,SYM,249,249,249,249,249, /* CX */
  SYM,SYM,SYM,SYM,SYM,SYM,SYM,SYM,249,249,249,249,SYM,SYM,249,249, /* DX */
  249, 22,SYM,SYM, 22,249,249, 32,249,249, 30, 23, 23,249, 31, 35, /* EX */
  249,249, 39,249,249,249,249,249, 41, 41,249,249,249,249,249,SYM, /* FX */
};
/*X0  X1  X2  X3  X4  X5  X6  X7  X8  X9  XA  XB  XC  XD  XE  XF */


/* Model Table:
 * Total sequences: 734
 * First 512 sequences: 0.998142344478184
 * Next 512 sequences (512-1024): 0.0018576555218160855
 * Rest: -3.707971429900425e-17
 * Negative sequences: TODO
 */
static const PRUint8 SloveneLangModel[] =
{
  2,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,2,
  3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,2,
  3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,0,2,3,2,
  3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,0,
  3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,2,3,3,3,3,3,2,2,2,
  3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,2,0,3,
  3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,2,3,3,3,0,0,0,3,3,3,2,0,
  3,3,3,3,3,3,3,3,3,2,3,3,3,3,3,2,3,2,3,3,3,2,2,0,3,3,3,2,3,
  3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,2,3,3,3,3,2,3,2,3,3,3,2,2,0,
  3,3,3,3,3,2,3,3,0,0,3,3,3,3,3,2,3,2,3,3,3,2,3,0,0,0,0,0,0,
  3,3,3,3,3,3,3,3,3,3,0,3,3,3,3,3,3,3,0,3,3,3,3,2,2,2,0,2,0,
  3,3,3,3,3,3,3,3,3,3,3,2,2,3,3,2,3,0,2,3,3,0,3,0,2,3,2,0,0,
  3,3,3,3,3,3,3,3,3,2,0,3,3,3,2,2,3,3,3,3,3,2,2,0,2,3,0,0,2,
  3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,2,3,3,2,2,2,3,2,2,0,
  3,3,3,3,3,3,2,3,3,3,2,3,3,3,3,0,3,2,3,3,2,2,3,0,2,3,2,2,0,
  3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,3,2,3,2,3,2,0,2,2,2,0,
  3,3,3,2,3,3,3,3,3,3,3,3,3,3,3,3,2,3,3,3,3,3,3,3,3,2,0,3,0,
  3,3,3,3,3,3,2,3,3,0,3,0,3,2,2,0,3,2,3,2,3,0,0,0,2,2,2,2,0,
  3,3,3,3,3,3,3,3,3,3,3,2,2,3,3,0,3,0,2,2,0,3,2,2,2,3,2,0,0,
  3,3,3,3,2,3,3,3,3,0,2,3,3,3,2,2,3,2,2,3,3,0,0,0,2,3,2,2,2,
  3,3,3,3,3,3,3,2,3,0,3,3,2,3,2,2,3,0,2,0,0,2,0,0,2,2,2,0,0,
  3,3,3,3,3,3,2,0,3,3,2,3,2,2,0,2,3,0,2,2,0,0,2,0,2,0,0,0,0,
  3,3,3,3,3,2,3,0,3,3,2,3,3,0,0,0,3,0,0,0,0,3,0,2,0,0,0,0,0,
  3,3,3,2,3,2,0,0,3,3,2,3,0,0,0,0,3,2,3,2,0,0,0,0,0,0,0,0,0,
  3,3,3,3,2,3,3,3,3,0,0,0,0,2,3,0,3,2,2,2,0,0,0,0,3,2,2,0,0,
  3,3,2,3,3,2,3,3,3,3,0,2,2,2,2,0,2,2,2,3,2,0,0,0,0,0,2,2,0,
  3,3,3,3,3,2,0,3,2,0,0,0,0,0,2,0,2,2,2,2,2,0,0,0,2,2,3,0,0,
  3,3,3,3,2,2,3,2,0,0,2,0,3,2,2,0,3,2,3,3,2,0,0,0,2,2,2,2,0,
  0,0,2,0,2,0,2,0,2,0,0,0,0,0,0,0,3,0,0,0,0,0,0,0,0,0,0,0,0,
};


const SequenceModel Iso_8859_2SloveneModel =
{
  Iso_8859_2_CharToOrderMap,
  SloveneLangModel,
  29,
  (float)0.998142344478184,
  PR_TRUE,
  "ISO-8859-2"
};

const SequenceModel Iso_8859_16SloveneModel =
{
  Iso_8859_16_CharToOrderMap,
  SloveneLangModel,
  29,
  (float)0.998142344478184,
  PR_TRUE,
  "ISO-8859-16"
};

const SequenceModel Windows_1250SloveneModel =
{
  Windows_1250_CharToOrderMap,
  SloveneLangModel,
  29,
  (float)0.998142344478184,
  PR_TRUE,
  "WINDOWS-1250"
};

const SequenceModel Ibm852SloveneModel =
{
  Ibm852_CharToOrderMap,
  SloveneLangModel,
  29,
  (float)0.998142344478184,
  PR_TRUE,
  "IBM852"
};

const SequenceModel MaccentraleuropeSloveneModel =
{
  Maccentraleurope_CharToOrderMap,
  SloveneLangModel,
  29,
  (float)0.998142344478184,
  PR_TRUE,
  "MacCentralEurope"
};