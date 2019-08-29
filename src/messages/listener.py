from antlr4 import TerminalNode
from src.messages.message_parserListener import message_parserListener
from src.messages.message_parser import message_parser

class Listener(message_parserListener):
    def __init__(self, message, args, kwargs):
        super().__init__()
        self._value = None
        self.nest_level = 0
        self.used_args = set()
        self.message = message
        self.args = args
        self.kwargs = kwargs

    def value(self):
        if self._value is None:
            raise ValueError("Parse error: {}: Unexpected end of message".format(self.message.key))
        return self._value

    def _join_fragments(self, fragments, *, enforce_string=False):
        # fragments is typically a generator function but we need to access values multiple times
        fragment_list = list(fragments)
        if not enforce_string and len(fragment_list) == 1:
            return fragment_list[0]

        bits = []
        for node in fragment_list:
            if isinstance(node, TerminalNode):
                bits.append(node.getText())
            else:
                bits.append(str(node.value))

        return "".join(bits)

    def _coalesce(self, *args, default=None):
        for thing in args:
            if thing is None:
                continue
            if isinstance(thing, TerminalNode):
                return thing.getText()
            return thing.value

        return default

    def exitMain(self, ctx: message_parser.MainContext):
        self._value = ctx.string().value
        self.message.formatter.check_unused_args(self.used_args, self.args, self.kwargs)

    def exitString(self, ctx: message_parser.StringContext):
        ctx.value = self._join_fragments(ctx.getChildren(), enforce_string=True)

    def exitTag(self, ctx: message_parser.TagContext):
        # to resolve a tag, we call the relevant function on our formatter, passing in the
        # parameter (if any) and tag content
        tag_name, param = ctx.open_tag().value  # param may be None
        content = ctx.string().value
        close_name = ctx.close_tag().value

        if tag_name != close_name:
            # mismatch of tag names
            raise ValueError("Parse error: {}: Opening tag {} ({}) does not match closing tag {} ({})".format(
                             self.message.key, tag_name, ctx.open_tag().OPEN_TAG().getSymbol().column,
                             close_name, ctx.close_tag().CLOSE_TAG().getSymbol().column))

        tag_func = getattr(self.message.formatter, "tag_" + tag_name, None)
        if not tag_func or not callable(tag_func):
            raise ValueError("Parse error: {}: Unknown tag {} ({})".format(
                             self.message.key, tag_name, ctx.open_tag().OPEN_TAG().getSymbol().column))

        ctx.value = tag_func(content, param)

    def exitOpen_tag(self, ctx: message_parser.Open_tagContext):
        ctx.value = (ctx.TAG_NAME().getText(), self._coalesce(ctx.tag_param()))

    def exitTag_param(self, ctx: message_parser.Tag_paramContext):
        ctx.value = self._join_fragments(ctx.tag_param_frag())

    def exitTag_param_frag(self, ctx: message_parser.Tag_param_fragContext):
        ctx.value = self._coalesce(ctx.sub(), ctx.TAG_PARAM())

    def exitClose_tag(self, ctx: message_parser.Close_tagContext):
        ctx.value = ctx.TAG_NAME().getText()

    def enterSub(self, ctx: message_parser.SubContext):
        self.nest_level += 1

    def exitSub(self, ctx: message_parser.SubContext):
        self.nest_level -= 1
        flatten_lists = self.nest_level == 0

        field_name = ctx.sub_field().value
        convert = self._coalesce(ctx.sub_convert())
        spec = dict(x.value for x in ctx.sub_spec())
        # if spec is empty, change it to None. Makes us more consistent with built in format method
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
        ctx.value = obj

    def exitSub_field(self, ctx: message_parser.Sub_fieldContext):
        ctx.value = self._join_fragments(ctx.sub_field_frag())

    def exitSub_field_frag(self, ctx: message_parser.Sub_field_fragContext):
        ctx.value = self._coalesce(ctx.sub(), ctx.SUB_FIELD())

    def exitSub_convert(self, ctx: message_parser.Sub_convertContext):
        ctx.value = ctx.SUB_IDENTIFIER().getText()

    def exitSub_spec(self, ctx: message_parser.Sub_specContext):
        ctx.value = ctx.spec_value().value

    def exitSpec_value(self, ctx: message_parser.Spec_valueContext):
        ctx.value = self._coalesce(ctx.spec_func(), ctx.spec_literal())

    def exitSpec_literal(self, ctx: message_parser.Spec_literalContext):
        ctx.value = (self._join_fragments(ctx.spec_literal_frag(), enforce_string=True), None)

    def exitSpec_literal_frag(self, ctx: message_parser.Spec_literal_fragContext):
        ctx.value = self._coalesce(ctx.sub(), ctx.SPEC_VALUE())

