import asyncio


async def bind_reader_writer(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter
):
    while True:
        try:
            data = await reader.read(1024)
            if not data:
                break
            writer.write(data)
        except Exception as e:
            print(f"Error in bind_reader_writer: {e}")
            await writer.drain()
            break
