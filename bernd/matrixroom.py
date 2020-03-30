import asyncio
import nio
import pathlib
import logging
import importlib
from itertools import compress

from pathlib import Path

nio.RoomMember.get_friendly_name = lambda self: self.display_name


class MatrixRoom():

    class Plugin:
        def __init__(self, mroom, pluginid, pluginname):
            self.mroom = mroom
            self.pluginid = pluginid
            self.pluginname = pluginname
            self.handlers = []
            self.module = None

        async def load(self):
            filename = self.pluginname + "_plugin.py"
            plugin_path = Path(self.mroom.bot.plugindir).resolve()
            logging.info(f"Room {self.mroom.nio_room.room_id}: trying to load {plugin_path / filename}")
            if (plugin_path / filename).exists():
                modname = f'plugins.{self.pluginname}'
                loader = importlib.machinery.SourceFileLoader(modname,
                        str(plugin_path/filename))
                try:
                    self.module = loader.load_module(modname)
                    self.module.ENVIRONMENT = self.mroom.bot.environment.copy()
                    self.module.register_to(self)
                    return True
                except Exception as e:
                    logging.warning(str(e))
                    return False
            else:
                logging.warning(f"""
                Room {self.mroom.room_id}: couldn't load plugin {self.pluginname}: file does not exist
                """)
                return False

        def add_handler(self, handler):
            self.handlers.append(handler)

        async def test_callback(self, event):
            """
            TODO: change this architecture
            TODO: add try catch and print to room
            """
            self.handler_results = [handler.test_callback(self.mroom, event.source) for handler in self.handlers]
            print(self.handlers)
            return any(self.handler_results)
        
        async def handle_callback(self, event):
            """
            TODO: add try catch and print to room
            """
            totrigger = compress(self.handlers,self.handler_results)
            for handler in totrigger:
                await handler.handle_callback(self.mroom, event.source)


    async def load_plugins(self):
        c = self.bot.conn.cursor()
        r = c.execute("""
        SELECT pluginid,pluginname
        FROM rooms JOIN room_plugins ON rooms.roomid == room_plugins.roomid
        WHERE rooms.roomid=?;
        """, (self.room_id,))

        # construct plugins
        self.plugins = []
        for pid,pname in r.fetchall():
            self.plugins.append(MatrixRoom.Plugin(self,pid,pname))

        # load plugins
        results = await asyncio.gather(*(p.load() for p in self.plugins))
        self.plugins = list(compress(self.plugins,results))


    async def handle_text_event(self, event):
        results = await asyncio.gather(*(p.test_callback(event)
            for p in self.plugins))
        await asyncio.gather(*(p.handle_callback(event)
            for p in compress(self.plugins,results)))



    def __init__(self, matrixbot, nio_room):
        self.bot = matrixbot
        self.nio_room = nio_room
        self.room_id = nio_room.room_id
        self.client = matrixbot.client

    @classmethod
    async def new(cls, bot, nio_room):
        """
        call this when bot enters a new room
        """
        c = bot.conn.cursor()
        r = c.execute("""
        INSERT INTO rooms
        SELECT (?)
        WHERE NOT EXISTS (SELECT * FROM rooms
                          WHERE roomid = ?);
        """, (nio_room.room_id,nio_room.room_id,))
        bot.conn.commit()

        room = cls(bot, nio_room)
        await room.load_plugins()
        await room.introduce_bot()
        await room.add_plugin("help")
        await room.add_plugin("meta")
        return room

    async def add_plugin(self, pluginname):
        if not pluginname in self.bot.available_plugins:
            loggin.warning(f"{self.roomid} tried to load invalid plugin {pluginname}")
            return
        c = self.bot.conn.cursor()
        r = c.execute("""
        INSERT INTO room_plugins(roomid,pluginname)
        VALUES (?,?); 
        """, (self.room_id, pluginname))
        self.bot.conn.commit()
        r = c.execute("""
        SELECT last_insert_rowid();
        """)
        pid, = r.fetchall()

        plugin = MatrixRoom.Plugin(self,pid,pluginname)
        await plugin.load()
        self.plugins.append(plugin)

    async def remove_plugin(self, pluginname):
        c = self.bot.conn.cursor()
        indizes = [i for (i,p) in enumerate(self.plugins) if p.pluginname==pluginname]
        if indizes:
            r = c.execute("""
            DELETE FROM room_plugins
            WHERE roomid=? AND pluginname=?;
            """, (self.room_id, pluginname))
            self.bot.conn.commit()
            del self.plugins[indizes[0]]


    #=============================================
    # Plugin helper functions
    #==============================================
    async def introduce_bot(self):
        try:
            logging.info(f"Introducing myself to {self.nio_room.room_id}")
            await self.send_text(f"""Hi, my name is {self.bot.botname}! I was just (re)started. Type !help to see my (new) capabilities.""")
        except Exception as e:
            logging.info(f"Exception: {e}")



    async def send_html(self, formatted_txt, txt=""):
        response = await self.client.room_send(
                room_id=self.nio_room.room_id,
                message_type="m.room.message",
                content={
                    "msgtype": "m.text",
                    "format": "org.matrix.custom.html",
                    "formatted_body" : formatted_txt,
                    "body": txt,
                },
                ignore_unverified_devices=True)
        logging.debug(response)

    async def send_text(self, txt):
        await self.client.room_send(
                room_id=self.nio_room.room_id,
                message_type="m.room.message",
                content={
                    "msgtype": "m.text",
                    "body": txt,
                },
                ignore_unverified_devices=True)

    async def send_notice(self, txt):
        await self.client.room_send(
                room_id=self.nio_room.room_id,
                message_type="m.room.message",
                content={
                    "msgtype": "m.notice",
                    "body": txt,
                },
                ignore_unverified_devices=True)

    async def get_joined_members(self):
        """
        TODO: return right strings
        """
        k = await self.client.joined_members(self.nio_room.room_id)
        return k.members


    async def send_image(self, filename):
        p = pathlib.Path(filename)
        extension = p.suffix.lower()[1:]
        if extension not in ["gif", "png", "jpg", "jpeg"]:
            raise Exception(f"Unsupported image format: {extension}")
        mime = "image/{}".format(extension.replace("jpeg", "jpg"))
        #print(f"{mime=}")
        uresp,fdi = await self.client.upload(lambda x,y: filename,
                content_type=mime,
                filename=p.name,
                encrypt=self.nio_room.encrypted)
        if not type(uresp) == nio.UploadResponse:
            print("Unable to upload image")
        else:
            # TODO: add preview
            uri = uresp.content_uri
            c = {
                    "msgtype": "m.image",
                    "body": p.name,
                    "info" : {"mimetype" : mime} # can be extended
                }

            if self.nio_room.encrypted:
                c["mimetype"]  = mime
                if fdi:
                    fdi["url"] = uri
                    fdi["mimetype"] = mime
                    c["file"] = fdi
                else:
                    c["file"] = {"url" : uri, "mimetype" : mime}
                #print(fdi)
            else:
                c["url"] = uri

            await self.client.room_send(
                    room_id=self.nio_room.room_id,
                    message_type="m.room.message",
                    content=c,
                    ignore_unverified_devices=True)
