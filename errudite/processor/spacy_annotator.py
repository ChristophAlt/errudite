import pkg_resources
from pathlib import Path
from typing import List

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)  # pylint: disable=invalid-name

from ..utils import dump_caches, load_caches, build_cached_path

try:
    import spacy
    from spacy.cli.download import download as spacy_download
    from spacy import util
    from spacy.tokens import Doc, Token
    from spacy.symbols import ORTH, LEMMA, POS, TAG
    try:
        spacy_version = int(spacy.__version__[0])
    except:
        spacy_version = 2
    if not Doc.has_extension('paraphrases'):
        Doc.set_extension('paraphrases', default=[], force=True)
except:
    raise Exception("spaCy not installed. Use `pip install spacy`.")

from .ling_consts import STOP_WORDS_semantic as STOP_WORDS


class NoOpTokenizer(object):
    def __init__(self, vocab):
        self.vocab = vocab

    def __call__(self, text):
        words = text
        # All tokens 'own' a subsequent space character in this tokenizer
        spaces = [True] * len(words)
        return Doc(self.vocab, words=words, spaces=spaces)


class WhitespaceTokenizer(object):
    def __init__(self, vocab):
        self.vocab = vocab

    def __call__(self, text):
        words = text.split(' ')
        # All tokens 'own' a subsequent space character in this tokenizer
        spaces = [True] * len(words)
        return Doc(self.vocab, words=words, spaces=spaces)


class SpacyAnnotator(object):
    """Annotator based on spacy.io
    
    Keyword Arguments:
        lang {str} -- language (default: {'en'})
        disable {List[str]} -- If only using tokenizer, can disable ['parser', 'ner', 'textcat'] (default: {None})
    """

    # if should disable certain steps: ['parser', 'ner', 'textcat']
    def __init__(self,
                 disable: List[str] = None,
                 pre_tokenized: bool = False,
                 use_whitespace: bool = False,
                 lang: str = "en_core_web_sm"):  # en_coref_sm
        disable = disable or []
        self.model = SpacyAnnotator.load_lang_model(lang, disable=disable)
        # special cases 
        # self.model.tokenizer.add_special_case(u"[TLE]", _build_special_case_rule("[TLE]"))
        # self.model.tokenizer.add_special_case(u"[DOC]", _build_special_case_rule("[DOC]"))
        # self.model.tokenizer.add_special_case(u"[PAR]", _build_special_case_rule("[PAR]"))
        # self.model.tokenizer.add_special_case(u"</P>", _build_special_case_rule("</P>"))
        # self.model.tokenizer.add_special_case(u"<P>", _build_special_case_rule("<P>"))
        self.load()
        if use_whitespace:
            self.model.tokenizer = WhitespaceTokenizer(self.model.vocab)
        if pre_tokenized:
            self.model.tokenizer = NoOpTokenizer(self.model.vocab)

    def dump(self):
        dump_caches(build_cached_path('vocab.pkl'),  self.model.vocab.to_bytes())

    def load(self):
        try:
            vocab = load_caches(build_cached_path('vocab.pkl'))
        except Exception as e:
            vocab = None
            logger.warn(e.args)
        if vocab:
            self.model.vocab.from_bytes(vocab)

    def process_text(self, sentence: str) -> Doc: 
        """Annotate a sentence with spacy

        Arguments:
            sentence {str} -- a string sentence

        Returns:
            Doc -- Annotated.
        """
        return self.model(sentence)

    def remove_stopwords(self, sentence_str: str=None, tokens: List[Token]=None, use_lemma: bool=True) -> str:
        """Function which gets a normalized string of the sentence and removes stop words

        Keyword Arguments:
            sentence_str {str} -- input sentence string (default: {None})
            tokens {List[Token]} -- pre-computed token list, with feature added (default: {None})
            use_lemma {bool} -- return the lemma or the text (default: {True})

        Returns:
            str -- the str with stopwords removed
        """
        if not tokens and sentence_str:
            #sentence_str = normalize_answer(sentence_str)
            tokens = self.model(sentence_str)
        elif not tokens:
            tokens = []
        #word_tokenize(sentence_str)
        attr = 'lemma_' if use_lemma else 'text' # what to merge
        return ' '.join([ getattr(token, attr) for token in tokens
            if not token.is_punct and token.text not in STOP_WORDS and token.lemma_ not in STOP_WORDS])

    @staticmethod
    def is_package(name: str):
        """Check if string maps to a package installed via pip.
        From https://github.com/explosion/spaCy/blob/master/spacy/util.py
        
        Arguments:
            name {str} -- Name of package
        
        Returns:
            [bool] -- True if installed package, False if not.
        """

        name = name.lower()  # compare package name against lowercase name
        packages = pkg_resources.working_set.by_key.keys()
        for package in packages:
            if package.lower().replace('-', '_') == name:
                return True
            return False

    @staticmethod
    def model_installed(name: str):
        """Check if spaCy language model is installed
        From https://github.com/explosion/spaCy/blob/master/spacy/util.py

        Arguments:
            name {str} -- Name of package

        Returns:
            [bool] -- True if installed package, False if not.
        """
        data_path = util.get_data_path()
        if not data_path or not data_path.exists():
            raise IOError("Can't find spaCy data path: %s" % str(data_path))
        if name in set([d.name for d in data_path.iterdir()]):
            return True
        if SpacyAnnotator.is_package(name): # installed as package
            return True
        if Path(name).exists(): # path to model data directory
            return True
        return False

    @staticmethod
    def load_lang_model(lang: str, disable: List[str]):
        """Load spaCy language model or download if
            model is available and not installed

        Arguments:
            lang {str} -- language
            disable {List[str]} -- If only using tokenizer, can disable ['parser', 'ner', 'textcat']

        Returns:
            [type] -- [description]
        """
        if 'coref' in lang:
            try:
                return spacy.load(lang, disable=disable)
            except Exception as e:
                return SpacyAnnotator.load_lang_model(lang.split('_')[0], disable=disable)
        try:
            return spacy.load(lang, disable=disable)
        except OSError:
            logger.warning(f"Spacy models '{lang}' not found.  Downloading and installing.")
            spacy_download(lang)
            # NOTE(mattg): The following four lines are a workaround suggested by Ines for spacy
            # 2.1.0, which removed the linking that was done in spacy 2.0.  importlib doesn't find
            # packages that were installed in the same python session, so the way `spacy_download`
            # works in 2.1.0 is broken for this use case.  These four lines can probably be removed
            # at some point in the future, once spacy has figured out a better way to handle this.
            # See https://github.com/explosion/spaCy/issues/3435.
            from spacy.cli import link
            from spacy.util import get_package_path
            package_path = get_package_path(lang)
            link(lang, lang, model_path=package_path)
            return spacy.load(lang, disable=disable)
