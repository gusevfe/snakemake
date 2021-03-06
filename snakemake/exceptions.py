# -*- coding: utf-8 -*-

import os
import traceback
from tokenize import TokenError

from snakemake.logging import logger

__author__ = "Johannes Köster"


def format_error(
    ex, lineno, linemaps=None, snakefile=None, show_traceback=False):
    msg = str(ex)
    if linemaps and snakefile:
        lineno = linemaps[snakefile][lineno]
        if isinstance(ex, SyntaxError):
            msg = ex.msg
    location = (" in line {} of {}".format(lineno, snakefile)
        if lineno and snakefile else "")
    tb = ""
    if show_traceback:
        tb = "\n".join(format_traceback(cut_traceback(ex), linemaps=linemaps))
    return '{}{}{}{}'.format(
        ex.__class__.__name__,
        location,
        ":\n" + msg if msg else ".",
        "\n{}".format(tb) if show_traceback and tb else "")


def get_exception_origin(ex, linemaps):
    for file, lineno, _, _ in reversed(traceback.extract_tb(ex.__traceback__)):
        if file in linemaps:
            return lineno, file


def cut_traceback(ex):
    snakemake_path = os.path.dirname(__file__)
    for line in traceback.extract_tb(ex.__traceback__):
        dir = os.path.dirname(line[0])
        if not dir:
            dir = "."
        if not os.path.samefile(snakemake_path, dir):
            yield line


def format_traceback(tb, linemaps):
    for file, lineno, function, code in tb:
        if file in linemaps:
            lineno = linemaps[file][lineno]
        if code is not None:
            yield '  File "{}", line {}, in {}'.format(file, lineno, function)


def print_exception(ex, linemaps, print_traceback=True):
    """
    Print an error message for a given exception.

    Arguments
    ex -- the exception
    linemaps -- a dict of a dict that maps for each snakefile
        the compiled lines to source code lines in the snakefile.
    """
    #traceback.print_exception(type(ex), ex, ex.__traceback__)
    origin = get_exception_origin(ex, linemaps)
    if origin is not None:
        lineno, file = origin
        logger.critical(format_error(
            ex, lineno, linemaps=linemaps, snakefile=file,
            show_traceback=print_traceback))
        return
    if isinstance(ex, SyntaxError):
        logger.critical(format_error(
            ex, ex.lineno, linemaps=linemaps, snakefile=ex.filename,
            show_traceback=print_traceback))
    elif isinstance(ex, TokenError):
        logger.critical(format_error(
            ex, None,
            show_traceback=print_traceback))
    elif isinstance(ex, RuleException):
        for e in ex._include + [ex]:
            if not e.omit:
                logger.critical(format_error(
                    e, e.lineno, linemaps=linemaps, snakefile=e.filename,
                    show_traceback=print_traceback))
    elif isinstance(ex, WorkflowError):
        logger.critical(
            format_error(
                ex, ex.lineno, linemaps=linemaps, snakefile=ex.snakefile,
                show_traceback=print_traceback))
    elif isinstance(ex, KeyboardInterrupt):
        logger.warning("Cancelling snakemake on user request.")
    else:
        traceback.print_exception(type(ex), ex, ex.__traceback__)


class WorkflowError(Exception):

    @staticmethod
    def format_args(args):
        for arg in args:
            if isinstance(arg, str):
                yield arg
            else:
                yield "{}: {}".format(arg.__class__.__name__, str(arg))

    def __init__(self, *args, lineno=None, snakefile=None, rule=None):
        super().__init__("\n".join(self.format_args(args)))
        if rule is not None:
            self.lineno = rule.lineno
            self.snakefile = rule.snakefile
        self.lineno = lineno
        self.snakefile = snakefile


class WildcardError(WorkflowError):
    pass


class RuleException(Exception):
    """
    Base class for exception occuring withing the
    execution or definition of rules.
    """
    def __init__(self, message=None, include=None,
        lineno=None, snakefile=None, rule=None):
        """
        Creates a new instance of RuleException.

        Arguments
        message -- the exception message
        include -- iterable of other exceptions to be included
        lineno -- the line the exception originates
        snakefile -- the file the exception originates
        """
        super(RuleException, self).__init__(message)
        self._include = set()
        if include:
            for ex in include:
                self._include.add(ex)
                self._include.update(ex._include)
        if rule is not None:
            if lineno is None:
                lineno = rule.lineno
            if snakefile is None:
                snakefile = rule.snakefile

        self._include = list(self._include)
        self.lineno = lineno
        self.filename = snakefile
        self.omit = not message

    @property
    def messages(self):
        return map(str, (ex for ex in self._include + [self] if not ex.omit))


class MissingOutputException(RuleException):
    pass


class IOException(RuleException):
    def __init__(self, prefix, rule, files,
        include=None, lineno=None, snakefile=None):
        message = ("{} for rule {}:\n{}".format(
            prefix, rule, "\n".join(files)) if files else "")
        super().__init__(
            message=message, include=include, lineno=lineno,
            snakefile=snakefile, rule=rule)


class MissingInputException(IOException):
    def __init__(self, rule, files, include=None, lineno=None, snakefile=None):
        super().__init__(
            "Missing input files", rule, files, include,
            lineno=lineno, snakefile=snakefile)


class ProtectedOutputException(IOException):
    def __init__(self, rule, files, include=None, lineno=None, snakefile=None):
        super().__init__("Write-protected output files", rule, files, include,
            lineno=lineno, snakefile=snakefile)


class UnexpectedOutputException(IOException):
    def __init__(self, rule, files, include=None, lineno=None, snakefile=None):
        super().__init__("Unexpectedly present output files "
        "(accidentally created by other rule?)", rule, files, include,
        lineno=lineno, snakefile=snakefile)


class AmbiguousRuleException(RuleException):
    def __init__(self, filename, rule1, rule2, lineno=None, snakefile=None):
        super().__init__(
            "Rules {} and {} are ambiguous for the file {}.".format(
                rule1, rule2, filename),
            lineno=lineno, snakefile=snakefile)
        self.rule1, self.rule2 = rule1, rule2


class CyclicGraphException(RuleException):
    def __init__(self, repeatedrule, file, rule=None):
        super().__init__(
            "Cyclic dependency on rule {}.".format(repeatedrule), rule=rule)
        self.file = file


class MissingRuleException(RuleException):
    def __init__(self, file, lineno=None, snakefile=None):
        super().__init__(
            "No rule to produce {}.".format(file),
            lineno=lineno, snakefile=snakefile)


class UnknownRuleException(RuleException):
    def __init__(self, name, prefix="", lineno=None, snakefile=None):
        msg = "There is no rule named {}.".format(name)
        if prefix:
            msg = "{} {}".format(prefix, msg)
        super().__init__(
            msg,
            lineno=lineno, snakefile=snakefile)


class NoRulesException(RuleException):
    def __init__(self, lineno=None, snakefile=None):
        super().__init__(
            "There has to be at least one rule.",
            lineno=lineno, snakefile=snakefile)


class IncompleteFilesException(RuleException):
    def __init__(self, files):
        super().__init__(
            "The files below seem to be incomplete. "
            "If you are sure that certain files are not incomplete, "
            "mark them as complete with\n\n"
            "    snakemake --cleanup-metadata <filenames>\n\n"
            "To re-generate the files rerun your command with the "
            "--rerun-incomplete flag.\nIncomplete files:\n{}".format(
                "\n".join(files)))


class IOFileException(RuleException):
    def __init__(self, msg, lineno=None, snakefile=None):
        super().__init__(msg, lineno=lineno, snakefile=snakefile)


class ClusterJobException(RuleException):
    def __init__(self, job, jobid, jobscript):
        super().__init__(
            "Error executing rule {} on cluster (jobid: {}, jobscript: {}). "
            "For detailed error see the cluster log.".format(job.rule.name, jobid, jobscript),
            lineno=job.rule.lineno, snakefile=job.rule.snakefile)


class CreateRuleException(RuleException):
    pass


class TerminatedException(Exception):
    pass
