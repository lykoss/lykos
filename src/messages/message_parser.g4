parser grammar message_parser;
options { language = Python3; tokenVocab = message_lexer; }

main
    : string EOF
    ;

string
    : string TEXT
    | string tag
    | string sub
    |
    ;

tag
    : open_tag string close_tag
    ;

open_tag
    : OPEN_TAG TAG_NAME tag_param CLOSE_TAG
    ;

tag_param
    : tag_param TAG_PARAM
    | tag_param sub
    |
    ;

close_tag
    : OPEN_TAG TAG_SLASH TAG_NAME CLOSE_TAG
    ;

sub
    : OPEN_SUB sub_field sub_convert sub_spec CLOSE_SUB
    ;

sub_field
    : sub_field SUB_FIELD
    | sub_field sub
    | SUB_FIELD
    | sub
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
    | SPEC_VALUE
    | sub
    ;
