# Generated from D:/Code/lykos/src/messages\message_parser.g4 by ANTLR 4.7.2
# encoding: utf-8
from antlr4 import *
from io import StringIO
from typing.io import TextIO
import sys


def serializedATN():
    with StringIO() as buf:
        buf.write("\3\u608b\ua72a\u8133\ub9ed\u417c\u3be7\u7786\u5964\3\17")
        buf.write("`\4\2\t\2\4\3\t\3\4\4\t\4\4\5\t\5\4\6\t\6\4\7\t\7\4\b")
        buf.write("\t\b\4\t\t\t\4\n\t\n\4\13\t\13\3\2\3\2\3\2\3\3\3\3\3\3")
        buf.write("\3\3\3\3\3\3\3\3\7\3!\n\3\f\3\16\3$\13\3\3\4\3\4\3\4\3")
        buf.write("\4\3\5\3\5\3\5\3\5\3\5\3\6\3\6\3\6\3\6\3\6\7\6\64\n\6")
        buf.write("\f\6\16\6\67\13\6\3\7\3\7\3\7\3\7\3\7\3\b\3\b\3\b\3\b")
        buf.write("\3\b\3\b\3\t\3\t\3\t\5\tG\n\t\3\n\3\n\3\n\3\n\7\nM\n\n")
        buf.write("\f\n\16\nP\13\n\3\13\3\13\3\13\5\13U\n\13\3\13\3\13\3")
        buf.write("\13\3\13\7\13[\n\13\f\13\16\13^\13\13\3\13\2\6\4\n\22")
        buf.write("\24\f\2\4\6\b\n\f\16\20\22\24\2\2\2_\2\26\3\2\2\2\4\31")
        buf.write("\3\2\2\2\6%\3\2\2\2\b)\3\2\2\2\n.\3\2\2\2\f8\3\2\2\2\16")
        buf.write("=\3\2\2\2\20F\3\2\2\2\22H\3\2\2\2\24T\3\2\2\2\26\27\5")
        buf.write("\4\3\2\27\30\7\2\2\3\30\3\3\2\2\2\31\"\b\3\1\2\32\33\f")
        buf.write("\6\2\2\33!\7\3\2\2\34\35\f\5\2\2\35!\5\6\4\2\36\37\f\4")
        buf.write("\2\2\37!\5\16\b\2 \32\3\2\2\2 \34\3\2\2\2 \36\3\2\2\2")
        buf.write("!$\3\2\2\2\" \3\2\2\2\"#\3\2\2\2#\5\3\2\2\2$\"\3\2\2\2")
        buf.write("%&\5\b\5\2&\'\5\4\3\2\'(\5\f\7\2(\7\3\2\2\2)*\7\4\2\2")
        buf.write("*+\7\6\2\2+,\5\n\6\2,-\7\t\2\2-\t\3\2\2\2.\65\b\6\1\2")
        buf.write("/\60\f\5\2\2\60\64\7\7\2\2\61\62\f\4\2\2\62\64\5\16\b")
        buf.write("\2\63/\3\2\2\2\63\61\3\2\2\2\64\67\3\2\2\2\65\63\3\2\2")
        buf.write("\2\65\66\3\2\2\2\66\13\3\2\2\2\67\65\3\2\2\289\7\4\2\2")
        buf.write("9:\7\b\2\2:;\7\6\2\2;<\7\t\2\2<\r\3\2\2\2=>\7\5\2\2>?")
        buf.write("\7\n\2\2?@\5\20\t\2@A\5\22\n\2AB\7\r\2\2B\17\3\2\2\2C")
        buf.write("D\7\13\2\2DG\7\16\2\2EG\3\2\2\2FC\3\2\2\2FE\3\2\2\2G\21")
        buf.write("\3\2\2\2HN\b\n\1\2IJ\f\4\2\2JK\7\f\2\2KM\5\24\13\2LI\3")
        buf.write("\2\2\2MP\3\2\2\2NL\3\2\2\2NO\3\2\2\2O\23\3\2\2\2PN\3\2")
        buf.write("\2\2QR\b\13\1\2RU\7\17\2\2SU\5\16\b\2TQ\3\2\2\2TS\3\2")
        buf.write("\2\2U\\\3\2\2\2VW\f\6\2\2W[\7\17\2\2XY\f\5\2\2Y[\5\16")
        buf.write("\b\2ZV\3\2\2\2ZX\3\2\2\2[^\3\2\2\2\\Z\3\2\2\2\\]\3\2\2")
        buf.write("\2]\25\3\2\2\2^\\\3\2\2\2\13 \"\63\65FNTZ\\")
        return buf.getvalue()


class message_parser ( Parser ):

    grammarFileName = "message_parser.g4"

    atn = ATNDeserializer().deserialize(serializedATN())

    decisionsToDFA = [ DFA(ds, i) for i, ds in enumerate(atn.decisionToState) ]

    sharedContextCache = PredictionContextCache()

    literalNames = [ "<INVALID>", "<INVALID>", "'['", "'{'", "<INVALID>", 
                     "<INVALID>", "'/'", "']'", "<INVALID>", "'!'" ]

    symbolicNames = [ "<INVALID>", "TEXT", "OPEN_TAG", "OPEN_SUB", "TAG_NAME", 
                      "TAG_PARAM", "TAG_SLASH", "CLOSE_TAG", "SUB_FIELD", 
                      "SUB_CONVERT", "SUB_SPEC", "CLOSE_SUB", "SUB_IDENTIFIER", 
                      "SPEC_VALUE" ]

    RULE_main = 0
    RULE_string = 1
    RULE_tag = 2
    RULE_open_tag = 3
    RULE_tag_param = 4
    RULE_close_tag = 5
    RULE_sub = 6
    RULE_sub_convert = 7
    RULE_sub_spec = 8
    RULE_spec_value = 9

    ruleNames =  [ "main", "string", "tag", "open_tag", "tag_param", "close_tag", 
                   "sub", "sub_convert", "sub_spec", "spec_value" ]

    EOF = Token.EOF
    TEXT=1
    OPEN_TAG=2
    OPEN_SUB=3
    TAG_NAME=4
    TAG_PARAM=5
    TAG_SLASH=6
    CLOSE_TAG=7
    SUB_FIELD=8
    SUB_CONVERT=9
    SUB_SPEC=10
    CLOSE_SUB=11
    SUB_IDENTIFIER=12
    SPEC_VALUE=13

    def __init__(self, input:TokenStream, output:TextIO = sys.stdout):
        super().__init__(input, output)
        self.checkVersion("4.7.2")
        self._interp = ParserATNSimulator(self, self.atn, self.decisionsToDFA, self.sharedContextCache)
        self._predicates = None




    class MainContext(ParserRuleContext):

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def string(self):
            return self.getTypedRuleContext(message_parser.StringContext,0)


        def EOF(self):
            return self.getToken(message_parser.EOF, 0)

        def getRuleIndex(self):
            return message_parser.RULE_main

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterMain" ):
                listener.enterMain(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitMain" ):
                listener.exitMain(self)




    def main(self):

        localctx = message_parser.MainContext(self, self._ctx, self.state)
        self.enterRule(localctx, 0, self.RULE_main)
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 20
            self.string(0)
            self.state = 21
            self.match(message_parser.EOF)
        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class StringContext(ParserRuleContext):

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def string(self):
            return self.getTypedRuleContext(message_parser.StringContext,0)


        def TEXT(self):
            return self.getToken(message_parser.TEXT, 0)

        def tag(self):
            return self.getTypedRuleContext(message_parser.TagContext,0)


        def sub(self):
            return self.getTypedRuleContext(message_parser.SubContext,0)


        def getRuleIndex(self):
            return message_parser.RULE_string

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterString" ):
                listener.enterString(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitString" ):
                listener.exitString(self)



    def string(self, _p:int=0):
        _parentctx = self._ctx
        _parentState = self.state
        localctx = message_parser.StringContext(self, self._ctx, _parentState)
        _prevctx = localctx
        _startState = 2
        self.enterRecursionRule(localctx, 2, self.RULE_string, _p)
        try:
            self.enterOuterAlt(localctx, 1)
            self._ctx.stop = self._input.LT(-1)
            self.state = 32
            self._errHandler.sync(self)
            _alt = self._interp.adaptivePredict(self._input,1,self._ctx)
            while _alt!=2 and _alt!=ATN.INVALID_ALT_NUMBER:
                if _alt==1:
                    if self._parseListeners is not None:
                        self.triggerExitRuleEvent()
                    _prevctx = localctx
                    self.state = 30
                    self._errHandler.sync(self)
                    la_ = self._interp.adaptivePredict(self._input,0,self._ctx)
                    if la_ == 1:
                        localctx = message_parser.StringContext(self, _parentctx, _parentState)
                        self.pushNewRecursionContext(localctx, _startState, self.RULE_string)
                        self.state = 24
                        if not self.precpred(self._ctx, 4):
                            from antlr4.error.Errors import FailedPredicateException
                            raise FailedPredicateException(self, "self.precpred(self._ctx, 4)")
                        self.state = 25
                        self.match(message_parser.TEXT)
                        pass

                    elif la_ == 2:
                        localctx = message_parser.StringContext(self, _parentctx, _parentState)
                        self.pushNewRecursionContext(localctx, _startState, self.RULE_string)
                        self.state = 26
                        if not self.precpred(self._ctx, 3):
                            from antlr4.error.Errors import FailedPredicateException
                            raise FailedPredicateException(self, "self.precpred(self._ctx, 3)")
                        self.state = 27
                        self.tag()
                        pass

                    elif la_ == 3:
                        localctx = message_parser.StringContext(self, _parentctx, _parentState)
                        self.pushNewRecursionContext(localctx, _startState, self.RULE_string)
                        self.state = 28
                        if not self.precpred(self._ctx, 2):
                            from antlr4.error.Errors import FailedPredicateException
                            raise FailedPredicateException(self, "self.precpred(self._ctx, 2)")
                        self.state = 29
                        self.sub()
                        pass

             
                self.state = 34
                self._errHandler.sync(self)
                _alt = self._interp.adaptivePredict(self._input,1,self._ctx)

        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.unrollRecursionContexts(_parentctx)
        return localctx


    class TagContext(ParserRuleContext):

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def open_tag(self):
            return self.getTypedRuleContext(message_parser.Open_tagContext,0)


        def string(self):
            return self.getTypedRuleContext(message_parser.StringContext,0)


        def close_tag(self):
            return self.getTypedRuleContext(message_parser.Close_tagContext,0)


        def getRuleIndex(self):
            return message_parser.RULE_tag

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterTag" ):
                listener.enterTag(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitTag" ):
                listener.exitTag(self)




    def tag(self):

        localctx = message_parser.TagContext(self, self._ctx, self.state)
        self.enterRule(localctx, 4, self.RULE_tag)
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 35
            self.open_tag()
            self.state = 36
            self.string(0)
            self.state = 37
            self.close_tag()
        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class Open_tagContext(ParserRuleContext):

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def OPEN_TAG(self):
            return self.getToken(message_parser.OPEN_TAG, 0)

        def TAG_NAME(self):
            return self.getToken(message_parser.TAG_NAME, 0)

        def tag_param(self):
            return self.getTypedRuleContext(message_parser.Tag_paramContext,0)


        def CLOSE_TAG(self):
            return self.getToken(message_parser.CLOSE_TAG, 0)

        def getRuleIndex(self):
            return message_parser.RULE_open_tag

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterOpen_tag" ):
                listener.enterOpen_tag(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitOpen_tag" ):
                listener.exitOpen_tag(self)




    def open_tag(self):

        localctx = message_parser.Open_tagContext(self, self._ctx, self.state)
        self.enterRule(localctx, 6, self.RULE_open_tag)
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 39
            self.match(message_parser.OPEN_TAG)
            self.state = 40
            self.match(message_parser.TAG_NAME)
            self.state = 41
            self.tag_param(0)
            self.state = 42
            self.match(message_parser.CLOSE_TAG)
        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class Tag_paramContext(ParserRuleContext):

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def tag_param(self):
            return self.getTypedRuleContext(message_parser.Tag_paramContext,0)


        def TAG_PARAM(self):
            return self.getToken(message_parser.TAG_PARAM, 0)

        def sub(self):
            return self.getTypedRuleContext(message_parser.SubContext,0)


        def getRuleIndex(self):
            return message_parser.RULE_tag_param

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterTag_param" ):
                listener.enterTag_param(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitTag_param" ):
                listener.exitTag_param(self)



    def tag_param(self, _p:int=0):
        _parentctx = self._ctx
        _parentState = self.state
        localctx = message_parser.Tag_paramContext(self, self._ctx, _parentState)
        _prevctx = localctx
        _startState = 8
        self.enterRecursionRule(localctx, 8, self.RULE_tag_param, _p)
        try:
            self.enterOuterAlt(localctx, 1)
            self._ctx.stop = self._input.LT(-1)
            self.state = 51
            self._errHandler.sync(self)
            _alt = self._interp.adaptivePredict(self._input,3,self._ctx)
            while _alt!=2 and _alt!=ATN.INVALID_ALT_NUMBER:
                if _alt==1:
                    if self._parseListeners is not None:
                        self.triggerExitRuleEvent()
                    _prevctx = localctx
                    self.state = 49
                    self._errHandler.sync(self)
                    la_ = self._interp.adaptivePredict(self._input,2,self._ctx)
                    if la_ == 1:
                        localctx = message_parser.Tag_paramContext(self, _parentctx, _parentState)
                        self.pushNewRecursionContext(localctx, _startState, self.RULE_tag_param)
                        self.state = 45
                        if not self.precpred(self._ctx, 3):
                            from antlr4.error.Errors import FailedPredicateException
                            raise FailedPredicateException(self, "self.precpred(self._ctx, 3)")
                        self.state = 46
                        self.match(message_parser.TAG_PARAM)
                        pass

                    elif la_ == 2:
                        localctx = message_parser.Tag_paramContext(self, _parentctx, _parentState)
                        self.pushNewRecursionContext(localctx, _startState, self.RULE_tag_param)
                        self.state = 47
                        if not self.precpred(self._ctx, 2):
                            from antlr4.error.Errors import FailedPredicateException
                            raise FailedPredicateException(self, "self.precpred(self._ctx, 2)")
                        self.state = 48
                        self.sub()
                        pass

             
                self.state = 53
                self._errHandler.sync(self)
                _alt = self._interp.adaptivePredict(self._input,3,self._ctx)

        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.unrollRecursionContexts(_parentctx)
        return localctx


    class Close_tagContext(ParserRuleContext):

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def OPEN_TAG(self):
            return self.getToken(message_parser.OPEN_TAG, 0)

        def TAG_SLASH(self):
            return self.getToken(message_parser.TAG_SLASH, 0)

        def TAG_NAME(self):
            return self.getToken(message_parser.TAG_NAME, 0)

        def CLOSE_TAG(self):
            return self.getToken(message_parser.CLOSE_TAG, 0)

        def getRuleIndex(self):
            return message_parser.RULE_close_tag

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterClose_tag" ):
                listener.enterClose_tag(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitClose_tag" ):
                listener.exitClose_tag(self)




    def close_tag(self):

        localctx = message_parser.Close_tagContext(self, self._ctx, self.state)
        self.enterRule(localctx, 10, self.RULE_close_tag)
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 54
            self.match(message_parser.OPEN_TAG)
            self.state = 55
            self.match(message_parser.TAG_SLASH)
            self.state = 56
            self.match(message_parser.TAG_NAME)
            self.state = 57
            self.match(message_parser.CLOSE_TAG)
        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class SubContext(ParserRuleContext):

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def OPEN_SUB(self):
            return self.getToken(message_parser.OPEN_SUB, 0)

        def SUB_FIELD(self):
            return self.getToken(message_parser.SUB_FIELD, 0)

        def sub_convert(self):
            return self.getTypedRuleContext(message_parser.Sub_convertContext,0)


        def sub_spec(self):
            return self.getTypedRuleContext(message_parser.Sub_specContext,0)


        def CLOSE_SUB(self):
            return self.getToken(message_parser.CLOSE_SUB, 0)

        def getRuleIndex(self):
            return message_parser.RULE_sub

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterSub" ):
                listener.enterSub(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitSub" ):
                listener.exitSub(self)




    def sub(self):

        localctx = message_parser.SubContext(self, self._ctx, self.state)
        self.enterRule(localctx, 12, self.RULE_sub)
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 59
            self.match(message_parser.OPEN_SUB)
            self.state = 60
            self.match(message_parser.SUB_FIELD)
            self.state = 61
            self.sub_convert()
            self.state = 62
            self.sub_spec(0)
            self.state = 63
            self.match(message_parser.CLOSE_SUB)
        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class Sub_convertContext(ParserRuleContext):

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def SUB_CONVERT(self):
            return self.getToken(message_parser.SUB_CONVERT, 0)

        def SUB_IDENTIFIER(self):
            return self.getToken(message_parser.SUB_IDENTIFIER, 0)

        def getRuleIndex(self):
            return message_parser.RULE_sub_convert

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterSub_convert" ):
                listener.enterSub_convert(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitSub_convert" ):
                listener.exitSub_convert(self)




    def sub_convert(self):

        localctx = message_parser.Sub_convertContext(self, self._ctx, self.state)
        self.enterRule(localctx, 14, self.RULE_sub_convert)
        try:
            self.state = 68
            self._errHandler.sync(self)
            la_ = self._interp.adaptivePredict(self._input,4,self._ctx)
            if la_ == 1:
                self.enterOuterAlt(localctx, 1)
                self.state = 65
                self.match(message_parser.SUB_CONVERT)
                self.state = 66
                self.match(message_parser.SUB_IDENTIFIER)
                pass

            elif la_ == 2:
                self.enterOuterAlt(localctx, 2)

                pass


        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class Sub_specContext(ParserRuleContext):

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def sub_spec(self):
            return self.getTypedRuleContext(message_parser.Sub_specContext,0)


        def SUB_SPEC(self):
            return self.getToken(message_parser.SUB_SPEC, 0)

        def spec_value(self):
            return self.getTypedRuleContext(message_parser.Spec_valueContext,0)


        def getRuleIndex(self):
            return message_parser.RULE_sub_spec

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterSub_spec" ):
                listener.enterSub_spec(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitSub_spec" ):
                listener.exitSub_spec(self)



    def sub_spec(self, _p:int=0):
        _parentctx = self._ctx
        _parentState = self.state
        localctx = message_parser.Sub_specContext(self, self._ctx, _parentState)
        _prevctx = localctx
        _startState = 16
        self.enterRecursionRule(localctx, 16, self.RULE_sub_spec, _p)
        try:
            self.enterOuterAlt(localctx, 1)
            self._ctx.stop = self._input.LT(-1)
            self.state = 76
            self._errHandler.sync(self)
            _alt = self._interp.adaptivePredict(self._input,5,self._ctx)
            while _alt!=2 and _alt!=ATN.INVALID_ALT_NUMBER:
                if _alt==1:
                    if self._parseListeners is not None:
                        self.triggerExitRuleEvent()
                    _prevctx = localctx
                    localctx = message_parser.Sub_specContext(self, _parentctx, _parentState)
                    self.pushNewRecursionContext(localctx, _startState, self.RULE_sub_spec)
                    self.state = 71
                    if not self.precpred(self._ctx, 2):
                        from antlr4.error.Errors import FailedPredicateException
                        raise FailedPredicateException(self, "self.precpred(self._ctx, 2)")
                    self.state = 72
                    self.match(message_parser.SUB_SPEC)
                    self.state = 73
                    self.spec_value(0) 
                self.state = 78
                self._errHandler.sync(self)
                _alt = self._interp.adaptivePredict(self._input,5,self._ctx)

        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.unrollRecursionContexts(_parentctx)
        return localctx


    class Spec_valueContext(ParserRuleContext):

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def SPEC_VALUE(self):
            return self.getToken(message_parser.SPEC_VALUE, 0)

        def sub(self):
            return self.getTypedRuleContext(message_parser.SubContext,0)


        def spec_value(self):
            return self.getTypedRuleContext(message_parser.Spec_valueContext,0)


        def getRuleIndex(self):
            return message_parser.RULE_spec_value

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterSpec_value" ):
                listener.enterSpec_value(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitSpec_value" ):
                listener.exitSpec_value(self)



    def spec_value(self, _p:int=0):
        _parentctx = self._ctx
        _parentState = self.state
        localctx = message_parser.Spec_valueContext(self, self._ctx, _parentState)
        _prevctx = localctx
        _startState = 18
        self.enterRecursionRule(localctx, 18, self.RULE_spec_value, _p)
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 82
            self._errHandler.sync(self)
            token = self._input.LA(1)
            if token in [message_parser.SPEC_VALUE]:
                self.state = 80
                self.match(message_parser.SPEC_VALUE)
                pass
            elif token in [message_parser.OPEN_SUB]:
                self.state = 81
                self.sub()
                pass
            else:
                raise NoViableAltException(self)

            self._ctx.stop = self._input.LT(-1)
            self.state = 90
            self._errHandler.sync(self)
            _alt = self._interp.adaptivePredict(self._input,8,self._ctx)
            while _alt!=2 and _alt!=ATN.INVALID_ALT_NUMBER:
                if _alt==1:
                    if self._parseListeners is not None:
                        self.triggerExitRuleEvent()
                    _prevctx = localctx
                    self.state = 88
                    self._errHandler.sync(self)
                    la_ = self._interp.adaptivePredict(self._input,7,self._ctx)
                    if la_ == 1:
                        localctx = message_parser.Spec_valueContext(self, _parentctx, _parentState)
                        self.pushNewRecursionContext(localctx, _startState, self.RULE_spec_value)
                        self.state = 84
                        if not self.precpred(self._ctx, 4):
                            from antlr4.error.Errors import FailedPredicateException
                            raise FailedPredicateException(self, "self.precpred(self._ctx, 4)")
                        self.state = 85
                        self.match(message_parser.SPEC_VALUE)
                        pass

                    elif la_ == 2:
                        localctx = message_parser.Spec_valueContext(self, _parentctx, _parentState)
                        self.pushNewRecursionContext(localctx, _startState, self.RULE_spec_value)
                        self.state = 86
                        if not self.precpred(self._ctx, 3):
                            from antlr4.error.Errors import FailedPredicateException
                            raise FailedPredicateException(self, "self.precpred(self._ctx, 3)")
                        self.state = 87
                        self.sub()
                        pass

             
                self.state = 92
                self._errHandler.sync(self)
                _alt = self._interp.adaptivePredict(self._input,8,self._ctx)

        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.unrollRecursionContexts(_parentctx)
        return localctx



    def sempred(self, localctx:RuleContext, ruleIndex:int, predIndex:int):
        if self._predicates == None:
            self._predicates = dict()
        self._predicates[1] = self.string_sempred
        self._predicates[4] = self.tag_param_sempred
        self._predicates[8] = self.sub_spec_sempred
        self._predicates[9] = self.spec_value_sempred
        pred = self._predicates.get(ruleIndex, None)
        if pred is None:
            raise Exception("No predicate with index:" + str(ruleIndex))
        else:
            return pred(localctx, predIndex)

    def string_sempred(self, localctx:StringContext, predIndex:int):
            if predIndex == 0:
                return self.precpred(self._ctx, 4)
         

            if predIndex == 1:
                return self.precpred(self._ctx, 3)
         

            if predIndex == 2:
                return self.precpred(self._ctx, 2)
         

    def tag_param_sempred(self, localctx:Tag_paramContext, predIndex:int):
            if predIndex == 3:
                return self.precpred(self._ctx, 3)
         

            if predIndex == 4:
                return self.precpred(self._ctx, 2)
         

    def sub_spec_sempred(self, localctx:Sub_specContext, predIndex:int):
            if predIndex == 5:
                return self.precpred(self._ctx, 2)
         

    def spec_value_sempred(self, localctx:Spec_valueContext, predIndex:int):
            if predIndex == 6:
                return self.precpred(self._ctx, 4)
         

            if predIndex == 7:
                return self.precpred(self._ctx, 3)
         




