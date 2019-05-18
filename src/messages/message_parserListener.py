# Generated from D:/Code/lykos/src/messages\message_parser.g4 by ANTLR 4.7.2
from antlr4 import *
if __name__ is not None and "." in __name__:
    from .message_parser import message_parser
else:
    from message_parser import message_parser

# This class defines a complete listener for a parse tree produced by message_parser.
class message_parserListener(ParseTreeListener):

    # Enter a parse tree produced by message_parser#main.
    def enterMain(self, ctx:message_parser.MainContext):
        pass

    # Exit a parse tree produced by message_parser#main.
    def exitMain(self, ctx:message_parser.MainContext):
        pass


    # Enter a parse tree produced by message_parser#string.
    def enterString(self, ctx:message_parser.StringContext):
        pass

    # Exit a parse tree produced by message_parser#string.
    def exitString(self, ctx:message_parser.StringContext):
        pass


    # Enter a parse tree produced by message_parser#tag.
    def enterTag(self, ctx:message_parser.TagContext):
        pass

    # Exit a parse tree produced by message_parser#tag.
    def exitTag(self, ctx:message_parser.TagContext):
        pass


    # Enter a parse tree produced by message_parser#open_tag.
    def enterOpen_tag(self, ctx:message_parser.Open_tagContext):
        pass

    # Exit a parse tree produced by message_parser#open_tag.
    def exitOpen_tag(self, ctx:message_parser.Open_tagContext):
        pass


    # Enter a parse tree produced by message_parser#tag_param.
    def enterTag_param(self, ctx:message_parser.Tag_paramContext):
        pass

    # Exit a parse tree produced by message_parser#tag_param.
    def exitTag_param(self, ctx:message_parser.Tag_paramContext):
        pass


    # Enter a parse tree produced by message_parser#close_tag.
    def enterClose_tag(self, ctx:message_parser.Close_tagContext):
        pass

    # Exit a parse tree produced by message_parser#close_tag.
    def exitClose_tag(self, ctx:message_parser.Close_tagContext):
        pass


    # Enter a parse tree produced by message_parser#sub.
    def enterSub(self, ctx:message_parser.SubContext):
        pass

    # Exit a parse tree produced by message_parser#sub.
    def exitSub(self, ctx:message_parser.SubContext):
        pass


    # Enter a parse tree produced by message_parser#sub_convert.
    def enterSub_convert(self, ctx:message_parser.Sub_convertContext):
        pass

    # Exit a parse tree produced by message_parser#sub_convert.
    def exitSub_convert(self, ctx:message_parser.Sub_convertContext):
        pass


    # Enter a parse tree produced by message_parser#sub_spec.
    def enterSub_spec(self, ctx:message_parser.Sub_specContext):
        pass

    # Exit a parse tree produced by message_parser#sub_spec.
    def exitSub_spec(self, ctx:message_parser.Sub_specContext):
        pass


    # Enter a parse tree produced by message_parser#spec_value.
    def enterSpec_value(self, ctx:message_parser.Spec_valueContext):
        pass

    # Exit a parse tree produced by message_parser#spec_value.
    def exitSpec_value(self, ctx:message_parser.Spec_valueContext):
        pass


