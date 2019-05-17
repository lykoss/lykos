parser grammar message_parser;
options { language = Python3; tokenVocab = message_lexer; }

main
    : string EOF
    ;

string
    : string TEXT
    | string open_tag string close_tag
    | string sub
    |
    ;

open_tag
    : OPEN_TAG TAG_NAME TAG_PARAM? CLOSE_TAG
    ;

close_tag
    : OPEN_TAG TAG_SLASH TAG_NAME CLOSE_TAG
    ;

sub
    : OPEN_SUB SUB_FIELD? sub_convert sub_spec CLOSE_SUB
    ;

sub_convert
    : SUB_CONVERT SUB_IDENTIFIER
    |
    ;

sub_spec
    : sub_spec SUB_SPEC spec_value
    |
    ;

spec_value
    : spec_value SPEC_VALUE
    | spec_value sub
    |
    ;
