# -*- coding: utf-8 -*-
"""provides sequencing fetching from NCBI and Ensembl

"""

from __future__ import absolute_import, division, print_function, unicode_literals

import logging
import os
import re

import requests

from ..exceptions import HGVSDataNotAvailableError

logger = logging.getLogger(__name__)


class SeqFetcher(object):
    """This class is intended primarily as a mixin for HGVS data providers
    that doen't otherwise have access to sequence data.  It uses the
    fetch_seq() function in this module to fetch sequences from
    several sources; see that function for details.

    >> sf = SeqFetcher()

    >> sf.fetch_seq('NP_056374.2',0,10)
    'MESRETLSSS'

    """

    def __init__(self):
        # If HGVS_SEQREPO_DIR is defined, we use seqrepo for *all* sequences
        # Otherwise, we fall back to remote sequence fetching
        seqrepo_dir = os.environ.get("HGVS_SEQREPO_DIR")
        if seqrepo_dir:
            from biocommons.seqrepo import SeqRepo
            sr = SeqRepo(seqrepo_dir)

            def _fetch_seq_seqrepo(ac, start_i=None, end_i=None):
                return sr.fetch(ac, start_i, end_i)

            self.fetcher = _fetch_seq_seqrepo
            logger.info("Using SeqRepo({}) sequence fetching".format(seqrepo_dir))
        else:
            self.fetcher = self._fetch_seq_remote
            logger.info("Using remote sequence fetching")


    def fetch_seq(self, ac, start_i=None, end_i=None):
        return self.fetcher(ac, start_i, end_i)


    def _fetch_seq_ensembl(self, ac, start_i=None, end_i=None):
        """Fetch the specified sequence slice from Ensembl using the public
        REST interface.

        An interbase interval may be optionally provided with start_i and
        end_i. However, the Ensembl REST interface does not currently
        accept intervals, so the entire sequence is returned and sliced
        locally.

        >> len(_fetch_seq_ensembl('ENSP00000288602'))
        766

        >> _fetch_seq_ensembl('ENSP00000288602',0,10)
        u'MAALSGGGGG'

        >> _fetch_seq_ensembl('ENSP00000288602')[0:10]
        u'MAALSGGGGG'

        >> _fetch_seq_ensembl('ENSP00000288602',0,10) == _fetch_seq_ensembl('ENSP00000288602')[0:10]
        True

        """

        url_fmt = "http://rest.ensembl.org/sequence/id/{ac}"
        url = url_fmt.format(ac=ac)
        r = requests.get(url, headers={"Content-Type": "application/json"})
        r.raise_for_status()
        seq = r.json()['seq']
        return seq if (start_i is None or end_i is None) else seq[start_i:end_i]


    def _fetch_seq_ncbi(self, ac, start_i=None, end_i=None):
        """Fetch sequences from NCBI using the eutils interface.  

        An interbase interval may be optionally provided with start_i and
        end_i. NCBI eutils will return just the requested subsequence,
        which might greatly reduce payload sizes (especially with
        chromosome-scale sequences).

        >> len(_fetch_seq_ncbi('NP_056374.2'))
        1596

        Pass the desired interval rather than using Python's [] slice
        operator.

        >> _fetch_seq_ncbi('NP_056374.2',0,10)
        'MESRETLSSS'

        >> _fetch_seq_ncbi('NP_056374.2')[0:10]
        'MESRETLSSS'

        >> _fetch_seq_ncbi('NP_056374.2',0,10) == _fetch_seq_ncbi('NP_056374.2')[0:10]
        True

        """

        url_fmt = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=nucleotide&id={ac}&rettype=fasta"
        if (start_i is None or end_i is None):
            url = url_fmt.format(ac=ac)
        else:
            url_fmt += "&seq_start={start}&seq_stop={stop}"
            url = url_fmt.format(ac=ac, start=start_i + 1, stop=end_i)
        resp = requests.get(url)
        resp.raise_for_status()
        return ''.join(resp.content.splitlines()[1:])


    def _fetch_seq_remote(self, ac, start_i=None, end_i=None):
        """return a subsequence of the given accession for the
        interbase interval [start_i,end_i)

        Fetches sequences from NCBI eutils and Ensembl REST interfaces
        (currently).  This class is primarily intended as a mixin for HGVS
        data providers that doen't otherwise have access to sequence data.

        Without an interval, the full sequence is returned::

        >> len(fetch_seq('NP_056374.2'))
        1596

        Therefore, it's preferable to provide the interval rather than
        using Python slicing sequence on the delivered sequence::

        >> fetch_seq('NP_056374.2',0,10)   # This!
        'MESRETLSSS'

        >> fetch_seq('NP_056374.2')[0:10]  # Not this!
        'MESRETLSSS'

        >> fetch_seq('NP_056374.2',0,10) == fetch_seq('NP_056374.2')[0:10]
        True

        Providing intervals is especially important for large sequences::

        >> fetch_seq('NC_000001.10',2000000,2000030)
        'ATCACACGTGCAGGAACCCTTTTCCAAAGG'

        This call will pull back 30 bases plus overhead; without the
        interval, one would receive 250MB of chr1 plus overhead.

        Essentially any RefSeq, Genbank, BIC, or Ensembl sequence may be
        fetched:

        >> [(ac,fetch_seq(ac,0,25))
        ... for ac in ['NG_032072.1', 'NW_003571030.1', 'NT_113901.1', 'NC_000001.10',
        ...            'NP_056374.2', 'GL000191.1', 'KB663603.1',
        ...            'ENST00000288602', 'ENSP00000288602']]
        [('NG_032072.1', 'AAAATTAAATTAAAATAAATAAAAA'),
         ('NW_003571030.1', 'TTGTGTGTTAGGGTGCTCTAAGCAA'),
         ('NT_113901.1', 'GAATTCCTCGTTCACACAGTTTCTT'),
         ('NC_000001.10', 'NNNNNNNNNNNNNNNNNNNNNNNNN'),
         ('NP_056374.2', 'MESRETLSSSRQRGGESDFLPVSSA'),
         ('GL000191.1', 'GATCCACCTGCCTCAGCCTCCCAGA'),
         ('KB663603.1', 'TTTATTTATTTTAGATACTTATCTC'),
         ('ENST00000288602', u'CGCCTCCCTTCCCCCTCCCCGCCCG'),
         ('ENSP00000288602', u'MAALSGGGGGGAEPGQALFNGDMEP')]

        >> fetch_seq('NM_9.9')
        Traceback (most recent call last):
           ...
        HGVSDataNotAvailableError: No sequence available for NM_9.9

        >> fetch_seq('QQ01234')
        Traceback (most recent call last):
           ...
        HGVSDataNotAvailableError: No fetcher for accessions like QQ01234

        """

        _ac_dispatch = [
            {'re': re.compile('^(?:AC|N[CGMPRTW])_|^[A-L]\w\d|^U\d'),
             'fetcher': self._fetch_seq_ncbi},
            {'re': re.compile('^ENS[TP]\d+'),
             'fetcher': self._fetch_seq_ensembl},
        ]

        for drec in _ac_dispatch:
            if drec['re'].match(ac):
                try:
                    return drec['fetcher'](ac, start_i, end_i)
                except requests.HTTPError:
                    raise HGVSDataNotAvailableError("No sequence available for {ac}".format(ac=ac))
        raise HGVSDataNotAvailableError("No fetcher for accessions like {}".format(ac))


# <LICENSE>
# Copyright 2013-2015 HGVS Contributors (https://bitbucket.org/biocommons/hgvs)
# 
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
#     http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# </LICENSE>
