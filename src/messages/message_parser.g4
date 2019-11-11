parser grammar message_parser;
options { language = Python3; tokenVocab = message_lexer; }

main : string EOF ;

string : ( TEXT | tag | sub )* ;

tag : open_tag string close_tag ;
open_tag : OPEN_TAG TAG_NAME tag_param? CLOSE_TAG ;
tag_param : TAG_SEP tag_param_frag+ ;
tag_param_frag : TAG_PARAM | sub ;
close_tag : OPEN_TAG TAG_SLASH TAG_NAME CLOSE_TAG ;

sub : OPEN_SUB sub_field sub_convert? sub_spec* CLOSE_SUB ;
sub_field : sub_field_frag+ ;
sub_field_frag : SUB_FIELD | sub ;
sub_convert : SUB_CONVERT SUB_IDENTIFIER ;
sub_spec : SUB_SPEC spec_value ;

spec_value : spec_func | spec_literal ;
spec_literal : spec_literal_frag+ ;
spec_literal_frag : SPEC_VALUE | sub ;
spec_func : SPEC_VALUE OPEN_ARGLIST spec_func_arg CLOSE_ARGLIST ;
spec_func_arg : spec_func_arg_frag+ ;
spec_func_arg_frag : ARGLIST_VALUE | sub ;
