
from app.http_reassembly import HTTPMessage, HTTPStreamParser
from app.message_broker import HTTPTransactionPublisher


class HTTPMessagePipeline:
    """Parse ordered HTTP byte chunks and publish completed messages."""

    def __init__(
        self,
        publisher: HTTPTransactionPublisher,
        parser: HTTPStreamParser | None = None,
    ):
        self.publisher = publisher
        self.parser = parser if parser is not None else HTTPStreamParser()

    def feed(self, data: bytes) -> list[HTTPMessage]:
        """Parse a chunk and publish every complete HTTP message."""
        messages = self.parser.feed(data)

        for message in messages:
            self.publisher.publish(message)

        return messages
