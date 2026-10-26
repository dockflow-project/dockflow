"""Require complete multipart bodies before accepting an uploaded payload."""

from starlette.formparsers import MultiPartException, MultiPartParser


class CompleteMultipartParser(MultiPartParser):
    complete = False

    def on_end(self):
        super().on_end()
        self.complete = True

    async def parse(self):
        form = await super().parse()
        if not self.complete:
            await form.close()
            raise MultiPartException("Incomplete multipart body")
        return form
