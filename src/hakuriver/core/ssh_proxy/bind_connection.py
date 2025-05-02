import asyncio


async def bind_reader_writer(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter
):
    while True:
        data = await reader.read(1024)
        if not data:
            break
        writer.write(data)