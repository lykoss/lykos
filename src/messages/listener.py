from src.messages.message_parserListener import message_parserListener
from src.messages.message_parser import message_parser


class Listener(message_parserListener):
    def __init__(self, message, args, kwargs):
        super().__init__()
        self.stack = []
        self.nest_level = 0
        self.used_args = set()
        self.message = message
        self.args = args
        self.kwargs = kwargs

    def value(self):
        if len(self.stack) != 1:
            raise ValueError("Parse error: {}: Unexpected end of message".format(self.message.key))
        return self.stack[0]

    def exitMain(self, ctx: message_parser.MainContext):
        self.message.formatter.check_unused_args(self.used_args, self.args, self.kwargs)

    def exitString(self, ctx: message_parser.StringContext):
        if ctx.getChildCount() == 0:
            self.stack.append("")
            return

        str1 = self.stack.pop()
        if ctx.TEXT() is not None:
            self.stack.append(str(str1) + ctx.TEXT().getText())
        else:
            # Note: if we have two arguments, they're reversed due to the nature of stacks
            # So, str2 actually appears first
            str2 = self.stack.pop()
            self.stack.append(str(str2) + str(str1))

    def exitTag(self, ctx: message_parser.TagContext):
        # to resolve a tag, we call the relevant function on our formatter, passing in the
        # parameter (if any) and tag content
        close_name = self.stack.pop()
        content = self.stack.pop()
        param = self.stack.pop()  # may be None
        tag_name = self.stack.pop()

        if tag_name != close_name:
            # mismatch of tag names
            raise ValueError("Parse error: {}: Opening tag {} ({}) does not match closing tag {} ({})".format(
                             self.message.key, tag_name, ctx.open_tag().OPEN_TAG().getSymbol().column,
                             close_name, ctx.close_tag().CLOSE_TAG().getSymbol().column))

        tag_func = getattr(self.message.formatter, "tag_" + tag_name, None)
        if not tag_func or not callable(tag_func):
            raise ValueError("Parse error: {}: Unknown tag {} ({})".format(
                             self.message.key, tag_name, ctx.open_tag().OPEN_TAG().getSymbol().column))

        value = tag_func(content, param)
        self.stack.append(value)

    def exitOpen_tag(self, ctx: message_parser.Open_tagContext):
        param = self.stack.pop()
        self.stack.append(ctx.TAG_NAME().getText())
        self.stack.append(param)

    def exitTag_param(self, ctx: message_parser.Tag_paramContext):
        if ctx.getChildCount() == 0:
            self.stack.append(None)
            return

        param1 = self.stack.pop()
        if ctx.TAG_PARAM() is not None:
            param2 = ctx.TAG_PARAM().getText()
            if param1 is not None:
                # Force prefix to be a string if we're adding in text
                # Otherwise if we're only doing a single substitution we support arbitrary data types
                # to pass to our tag formatter; we expect the formatter knows what to do with it and raises otherwise
                self.stack.append(str(param1) + param2)
            else:
                self.stack.append(param2)
        else:
            # param1 is the sub, param2 is the prefix
            param2 = self.stack.pop()
            if param2 is not None:
                # If we're combining two subs together, the only thing that makes sense is to make them both strings
                self.stack.append(str(param2) + str(param1))
            else:
                self.stack.append(param1)

    def exitClose_tag(self, ctx: message_parser.Close_tagContext):
        self.stack.append(ctx.TAG_NAME().getText())

    def enterSub(self, ctx: message_parser.SubContext):
        self.nest_level += 1

    def exitSub(self, ctx: message_parser.SubContext):
        self.nest_level -= 1
        flatten_lists = self.nest_level == 0
        spec = self.stack.pop()
        convert = self.stack.pop()
        field_name = self.stack.pop()
        # if spec is an empty list, change it to None. Makes us more consistent with built in format method
        # (since formatter can be used for both this parse tree as well as normal formatting)
        if not spec:
            spec = None
        # get_field internally calls get_value(), and then resolves attributes/indexes like 0.foo or 1[2]
        # the returned obj is end result of resolving all of that
        obj, key = self.message.formatter.get_field(field_name, self.args, self.kwargs)
        self.used_args.add(key)
        obj = self.message.formatter.convert_field(obj, convert)
        obj = self.message.formatter.format_field(obj, spec, flatten_lists=flatten_lists)
        # obj is not necessarily a string here; we support passing objects through until the point where we need
        # to concatenate them with other things (at which point we coerce to string)
        self.stack.append(obj)

    def exitSub_field(self, ctx:message_parser.Sub_fieldContext):
        if ctx.getChildCount() == 1:
            if ctx.SUB_FIELD() is not None:
                self.stack.append(ctx.SUB_FIELD().getText())
            # else: the top of the stack is the sub value, which we want to keep on top of stack, so do nothing
            return

        if ctx.SUB_FIELD() is not None:
            value = self.stack.pop()
            self.stack.append(str(value) + ctx.SUB_FIELD().getText())
        else:
            sub = self.stack.pop()
            value = self.stack.pop()
            self.stack.append(str(value) + str(sub))

    def exitSub_convert(self, ctx: message_parser.Sub_convertContext):
        if ctx.getChildCount() == 0:
            self.stack.append(None)
            return

        self.stack.append(ctx.SUB_IDENTIFIER().getText())

    def exitSub_spec(self, ctx: message_parser.Sub_specContext):
        if ctx.getChildCount() == 0:
            self.stack.append([])
            return

        value = self.stack.pop()
        spec = self.stack.pop()
        spec.append(value)
        self.stack.append(spec)

    def exitSpec_value(self, ctx: message_parser.Spec_valueContext):
        if ctx.getChildCount() == 1:
            if ctx.SPEC_VALUE() is not None:
                self.stack.append(ctx.SPEC_VALUE().getText())
            # else: the top of the stack is the sub value, which we want to keep on top of stack, so do nothing
            return

        if ctx.SPEC_VALUE() is not None:
            value = self.stack.pop()
            self.stack.append(str(value) + ctx.SPEC_VALUE().getText())
        else:
            sub = self.stack.pop()
            value = self.stack.pop()
            self.stack.append(str(value) + str(sub))
