/* -*- Mode: C; tab-width: 4; indent-tabs-mode: nil; c-basic-offset: 2 -*- */
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
 * The Original Code is Mozilla Universal charset detector code. This
 * file was later added by Jehan in 2021 to add language detection.
 *
 * The Initial Developer of the Original Code is Netscape Communications
 * Corporation.
 * Portions created by the Initial Developer are Copyright (C) 2001 the
 * Initial Developer. All Rights Reserved.
 *
 * Contributor(s):
 *          Jehan <zemarmot.net> (2021)
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

#include "nsLanguageDetector.h"

nsDetectState nsLanguageDetector::HandleData(const int* codePoints, PRUint32 cpLen)
{
  int order;

  for (PRUint32 i = 0; i < cpLen; i++)
  {
    order = GetOrderFromCodePoint(codePoints[i]);

    mTotalChar++;
#if 0
    /* TODO: detect illegal unicode codepoints. */
    if (order == ILL)
    {
      /* When encountering an illegal codepoint, no need
       * to continue analyzing data. It means this is not right, hence
       * that the encoding we deducted this codepoint from is wrong.
       */
      mState = STATE_UNLIKELY;
      break;
    }
    else if (order == CTR)
    {
      /* TODO: also detect ctrl character, as well as symbols and
       * punctuation, possibly return/line feeds and numbers. See how to
       * use these to improve language detection logics.
       * */
      mCtrlChar++;
    }
#endif

    /* Negative order represent non-frequent characters, yet not disqualifying.
     * We may also have a text with a bit of foreign quotes in it or
     * very unusual characters sometimes.
     */
    if (order >= 0 && order < mModel->freqCharCount)
    {
      mFreqChar++;

      if (mLastOrder >= 0 && mLastOrder < mModel->freqCharCount)
      {
        mTotalSeqs++;
        ++(mSeqCounters[mModel->precedenceMatrix[mLastOrder*mModel->freqCharCount+order]]);
      }
    }
    mLastOrder = order;
  }

  if (mState == STATE_DETECTING)
    if (mTotalSeqs > LANG_SB_ENOUGH_REL_THRESHOLD)
    {
      float cf = GetConfidence();
      if (cf > LANG_POSITIVE_SHORTCUT_THRESHOLD)
        mState = STATE_FOUND;
      else if (cf < LANG_NEGATIVE_SHORTCUT_THRESHOLD)
        mState = STATE_UNLIKELY;
    }

  return mState;
}

void nsLanguageDetector::Reset(void)
{
  mState     = STATE_DETECTING;
  mLastOrder = -1;
  for (PRUint32 i = 0; i < LANG_NUMBER_OF_SEQ_CAT; i++)
    mSeqCounters[i] = 0;
  mTotalSeqs = 0;
  mTotalChar = 0;
  mCtrlChar  = 0;
  mFreqChar  = 0;
}

float nsLanguageDetector::GetConfidence(void)
{
  float r;

  if (mTotalSeqs > 0) {
    /* Create a "logical" number of sequences rather than real, but
     * weighing the various sequences.
     * Basically positive sequences will boost the confidence, probable
     * sequence a bit, but not so much, neutral sequences will not be
     * integrated in the confidence.
     * Negative sequences will negatively impact the confidence as much
     * as positive sequence positively impact it.
     */
    int positiveSeqs = mSeqCounters[LANG_POSITIVE_CAT] * 4;
    int probableSeqs = mSeqCounters[LANG_PROBABLE_CAT];
    int neutralSeqs  = mSeqCounters[LANG_NEUTRAL_CAT];
    int negativeSeqs = mSeqCounters[LANG_NEGATIVE_CAT] * 4;
    int totalSeqs    = positiveSeqs + probableSeqs + neutralSeqs + negativeSeqs;

    r = ((float)1.0) * (positiveSeqs + probableSeqs - negativeSeqs) / totalSeqs / mModel->mTypicalPositiveRatio;
    /* The more control characters (proportionnaly to the size of the text), the
     * less confident we become in the current language.
     */
    r = r * (mTotalChar - mCtrlChar) / mTotalChar;
    r = r * mFreqChar / mTotalChar;

    return r;
  }
  return (float)0.01;
}

const char* nsLanguageDetector::GetLanguage()
{
  return mModel->langName;
}

int nsLanguageDetector::GetOrderFromCodePoint(int codePoint)
{
  int max = mModel->charOrderTableSize;
  int i   = max / 2;
  int c   = mModel->charOrderTable[i * 2];

  while ((c = mModel->charOrderTable[i * 2]) != codePoint)
  {
    if (c > codePoint)
    {
      if (i == 0)
        break;
      max = i - 1;
      i = i / 2;
    }
    else if (i < max - 1)
    {
      i += (max - i) / 2;
    }
    else if (i == max - 1)
    {
      i = max;
    }
    else
    {
      break;
    }
  }

  return (c == codePoint) ? mModel->charOrderTable[i * 2 + 1] : -1;
}
