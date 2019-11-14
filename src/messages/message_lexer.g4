lexer grammar message_lexer;
options { language = Python3; }

TEXT : (
    ~[[\]{}] { self.append_text() }
    | '{{' { self.append_text("{") }
    | '}}' { self.append_text("}") }
    | '[[' { self.append_text("[") }
    | ']]' { self.append_text("]") }
    )+ ;
OPEN_TAG : '[' -> pushMode(IN_TAG) ;
OPEN_SUB : '{' -> pushMode(IN_SUB) ;

mode IN_TAG;
TAG_NAME : [a-zA-Z]+ ;
TAG_SLASH : '/' ;
TAG_SEP : '=' -> mode(IN_TAG_PARAM) ;
CLOSE_TAG : ']' -> popMode ;

mode IN_TAG_PARAM;
TAG_PARAM : (
    ~[[\]{}] { self.append_text() }
    | '{{' { self.append_text("{") }
    | '}}' { self.append_text("}") }
    )+ ;
TAG_OPEN_SUB : '{' -> pushMode(IN_SUB), type(OPEN_SUB) ;
TAG_PARAM_CLOSE : ']' -> popMode, type(CLOSE_TAG) ;

mode IN_SUB;
SUB_FIELD : (
    ~[!:{}] { self.append_text() }
    | '{{' { self.append_text("{") }
    | '}}' { self.append_text("}") }
    )+ ;
SUB_CONVERT : '!' -> mode(IN_CONV) ;
SUB_SPEC : ':' -> mode(IN_SPEC) ;
SUB_OPEN_SUB : '{' -> pushMode(IN_SUB), type(OPEN_SUB) ;
CLOSE_SUB : '}' -> popMode ;

mode IN_CONV;
SUB_IDENTIFIER : [a-zA-Z]+ ;
CONV_SPEC : ':' -> mode(IN_SPEC), type(SUB_SPEC) ;
CLOSE_CONV : '}' -> popMode, type(CLOSE_SUB) ;

mode IN_SPEC;
SPEC_VALUE : (
    ~[:{}()] { self.append_text() }
    | '::' { self.append_text(":") }
    | '{{' { self.append_text("{") }
    | '}}' { self.append_text("}") }
    )+ ;
SPEC_SEP : ':' -> type(SUB_SPEC) ;
SPEC_OPEN_SUB : '{' -> pushMode(IN_SUB), type(OPEN_SUB) ;
OPEN_ARGLIST : '(' -> pushMode(IN_ARGLIST) ;
CLOSE_SPEC : '}' -> popMode, type(CLOSE_SUB) ;

mode IN_ARGLIST;
ARGLIST_VALUE : (
    ~[{}()] { self.append_text() }
    | '{{' { self.append_text("{") }
    | '}}' { self.append_text("}") }
    )+ ;
ARGLIST_OPEN_SUB : '{' -> pushMode(IN_SUB), type(OPEN_SUB) ;
CLOSE_ARGLIST : ')' -> popMode ;
