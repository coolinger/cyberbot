import re
import openai
import urllib
import json
import time
import logging
HELP_DESC = ("(automatic)\t\t\t-\tChat with me\n")

async def register_to(plugin):
    async def introduction():
        await plugin.send_html("Hello, I am a chatbot. Please talk to me. For real.")

    #test if being called from meta_plugin or from matrixroom
    if "chat_plugin" not in plugin.bot.config or "apikey" not in plugin.bot.config["chat_plugin"] or "prompt" not in plugin.bot.config["chat_plugin"]:
            logging.error("invite_manager: invalid config file section")
            return
    openai.api_key = plugin.bot.config["chat_plugin"]["apikey"]
    prompt = plugin.bot.config["chat_plugin"]["prompt"]

    async def image_edit_callback(room, event):
        #test if in thread
        if 'm.relates_to' in event['content'] and event['content']['m.relates_to']['rel_type'] == 'm.thread':
            #test if initial message is an image
            firstmessage=event['content']['m.relates_to']['event_id']
            firstmessage=await plugin.client.room_get_event(room.room_id, firstmessage)
            if firstmessage['msgtype'] == 'm.image':
                try:
                    chatgpt = openai.Image.create(

                    )
                except Exception as inst:
                    logging.error(inst)
                    response="Sorry, please come again?"
                else:
                    image_url=chatgpt['data'][0]['image_url']
                    #downlaod image
                    image=urllib.request.urlopen(image_url)
                    #upload image
                    await plugin.client.room_send(
                        room.room_id,
                        message_type="m.room.message",
                        content={
                            "msgtype": "m.image",
                            "body": "Image generated by GPT-3",
                            "url": image_url,
                            "info": {
                                "mimetype": "image/png",
                                "size": image.length,
                            },
                        },
                        ignore_unverified_devices=True,
                    )
    
    async def image_callback(room, event):
        #get text from event
        text=event['content']['body']
        #get prompt (everything after '!image')
        prompt=text.split(' ', 1)[1]
        #get image
        try:
            chatgpt = openai.Image.create(
                prompt=prompt,
                max_tokens=1024,
                temperature=0.5,
                n=1,
            )
        except Exception as inst:
            logging.error(inst)
            response="Sorry, please come again?"
        else:
            image_url=chatgpt['data'][0]['image_url']
            #downlaod image
            image=urllib.request.urlopen(image_url)
            #upload image
            await plugin.client.room_send(
                room.room_id,
                message_type="m.room.message",
                content={
                    "msgtype": "m.image",
                    "body": "Image generated by GPT-3",
                    "url": image_url,
                    "info": {
                        "mimetype": "image/png",
                        "size": image.length,
                    },
                },
                ignore_unverified_devices=True,
            )



                    

        
    async def gptanswer(room, prompt, engine="text-davinci-003", max_tokens=1024, stop=None, temperature=0.5, n=1, trigger=None):
        logging.info("Prompt: "+prompt)
        try:
            chatgpt = openai.Completion.create( engine=engine,prompt=prompt,max_tokens=max_tokens, temperature=temperature, n=n, stop=stop)
        except Exception as inst:
            logging.error(inst)
            response="Sorry, please come again?"
        else:
            response=chatgpt.choices[0].text
        logging.info("ChatGPT: "+json.dumps(chatgpt))
        logging.debug("Response: "+response)
        #return if response is empty
        if not response:
            logging.info("Response is empty")
            return
        if trigger:
            print(trigger.source)
            if 'm.relates_to' in trigger.source['content'] and trigger.source['content']['m.relates_to']['rel_type'] == 'm.thread':
                threadid=trigger.source['content']['m.relates_to']['event_id']
            else:
                threadid=trigger.source['event_id']
            content={
                "formatted_body": response,
                "body": response,
                "format": "org.matrix.custom.html",
                "msgtype": "m.text",
                "m.relates_to": {
                    "rel_type": "m.thread",
                    "event_id": threadid,
                    "is_falling_back": True,
                    "m.in_reply_to": {
                        "event_id": trigger.source['event_id']
                    }
                }
            }
            logging.debug("Content: "+json.dumps(content))
            await plugin.client.room_send(room_id=room,message_type="m.room.message",ignore_unverified_devices=True, content=content)
        else:
            await plugin.send_html(
                response
            )
        await plugin.client.room_typing(room, typing_state=False)

    async def chat_callback_test(room, event):
        logging.info("Event source: "+json.dumps(event.source))


    async def command_callback(room,event):
        print(event.source)

    async def reply_callback_textedit(room,event):
        #get quoted message
        input=re.search('(<mx-reply>.*</mx-reply>)(.*)', event.source['formatted_body']).group(1)
        #get instructions
        instructions=re.search('(<mx-reply>.*</mx-reply>).*!textedit (.*)', event.source['formatted_body']).group(2)

        await plugin.client.room_typing(room, typing_state=True)
        try:
            chatgpt=openai.Edit.create(model="text-davinci-edit-001", input=input, instructions=instructions)
            response=chatgpt['choices'][0]['text']
        except Exception as inst:
            logging.error(inst)
            response="Sorry, please come again?"
        else:
            await plugin.send_html(
                response
            )
        await plugin.client.room_typing(room, typing_state=False)


    def is_reply(room,event):
        if 'm.relates_to' in event.source['content'] and event.source['content']['m.relates_to']['rel_type'] == 'm.in_reply_to':
            return True
        return False

    async def callback_chooser(room,event):
        #pretty print event.__dict__
        print(json.dumps(event.__dict__, indent=4, sort_keys=True))
        print(room.__dict__)

        #handle all possible events



        #private chat and bot got an image
        if is_private_chat(room,event) and event.source['content']['msgtype'] == 'm.image':
            print("Private chat and image")
            #await image_edit_callback(room, event.source)
            return
        elif event.source['content']['msgtype'] == 'm.text':
            #test if reply
            if await is_reply_to_bot(room,event) or (is_private_chat(room,event) and is_reply(room,event)):
                #command assigned as reply
                if 'formatted_body' in event.source and re.search('<mx-reply>.*</mx-reply>', event.source['formatted_body']) and re.search('<mx-reply>.*</mx-reply>(.*)', event.source['formatted_body']).group(1).startswith('!'):
                    #get command
                    command=re.search('<mx-reply>.*</mx-reply>(.*)', event.source['formatted_body']).group(1).split(' ', 1)[0][1:]
                    #get function name
                    function_name="reply_command_callback_"+command
                    print("Command assigned as reply: "+function_name)
                    #check if function exists in this module
                    if function_name in globals():
                        print("Function exists: "+function_name)
                        #call function
                        #await globals()[function_name](room, event)
                        return
                    #check if command_callback_$command exists
                    elif "command_callback_"+command in globals():
                        print("Function exists: command_callback_"+command)
                        #call function
                        #await globals()["command_callback_"+command](room, event)
                        return
                #normal reply, get prompt from reply
                else:
                    print("Normal reply")
                    await chat_callback(room, event)
                    return

            #direct command, function command_callback_$command is availabe:
            elif event.source['content']['body'].startswith('!'):
                #get command
                command=event.source['content']['body'].split(' ', 1)[0][1:]
                #get function name
                function_name="command_callback_"+command
                print("Direct command: "+function_name)
                #check if function exists in this module
                if function_name in globals():
                    print("Function exists: "+function_name)
                    #call function
                    #await globals()[function_name](room, event)
                    return
            #message in private chat
            elif is_private_chat(room,event):
                print("Private chat")
                await chat_callback(room, event)
                return
            #message directed to bot
            elif event.source['content']['body'].startswith('@'+plugin.client.user_id.split(':')[0]) or \
                event.source['content']['body'].startswith(plugin.mroom.bot.botname+":"):
                print("Message directed to bot")
                await chat_callback(room, event)
                return
        print("Not handled")


    def is_thread(room,event):
        return 'm.relates_to' in event.source['content'] and event.source['content']['m.relates_to']['rel_type'] == 'm.thread'
    
    async def is_reply_to_bot(room,event):
        if 'm.relates_to' in event.source['content'] and event.source['content']['m.relates_to']['rel_type'] == 'm.in_reply_to':
            #get original message
            original_message=await plugin.client.room_get_event(room.room_id, event.source['content']['m.relates_to']['event_id'])
            #check if original message is from bot
            if original_message['sender'] == plugin.client.user_id:
                return True
        return False


    def is_private_chat(room,event):
        return len(room.nio_room.users.keys())==2 and \
            room.nio_room.own_user_id in room.nio_room.users.keys() and \
            [room.nio_room.users[user_id].power_level for user_id in room.nio_room.users.keys()] == [100,100] and \
            'type' in event.source and event.source['type']=='m.room.message' and \
            room.nio_room.own_user_id != event.source['sender']

    async def chat_callback(room, event):
        logging.debug("Event source: "+json.dumps(event.source))
        #return if sender is bot
        if event.sender == plugin.client.user_id:
            return
        await plugin.client.room_typing(room.room_id, typing_state=True)
        event_ids=[]
        if 'm.relates_to' in event.source['content'] and event.source['content']['m.relates_to']['rel_type'] == 'm.thread':
            path='/_matrix/client/v1/rooms/'+event.room_id+'/relations/'+event.source['content']['m.relates_to']['event_id']
            data={"access_token":plugin.client.access_token,"dir":"b","limit":20}
            query_string = urllib.parse.urlencode(data)
            path=path+'?'+query_string
            msgs=await plugin.client.send(method='GET', path=path)
            ciphered=await msgs.text()
            #print(ciphered)
            chunks=json.loads(ciphered)['chunk']
            #extract all [content][event_id] from chunks
            event_ids=[chunk['event_id'] for chunk in chunks]
            #add the base event_id to the list
            event_ids.append(event.source['content']['m.relates_to']['event_id'])
        else:
            event_ids.append(event.source['event_id'])
        #get all events
        eventrqs=[await plugin.client.room_get_event(event.room_id, event_id) for event_id in event_ids]
        events=[eventrq.event for eventrq in eventrqs]
        bodys=[]
        for _event in events:
            #get the displayname of the sender
            displayname=await plugin.client.get_displayname(_event.sender)
            #append displayname and body to bodys
            #test if _event has the attribute body
            if hasattr(_event, 'body'):
                bodys.append(displayname.displayname+": "+ _event.body)
            else:
                logging.error("Event has no body attribute")
                logging.error(_event)
        #reverse the list
        bodys.reverse()        
        #implode bodys separated by multipart
        thread_as_string="\n".join(bodys)
        fullprompt=prompt+"\n"+thread_as_string+"\nChatBot: "
        logging.debug("Full prompt: "+fullprompt)
        await gptanswer(room=event.room_id, prompt=fullprompt, trigger=event)

    chat_regex=plugin.RegexHandler(plugin.mroom.bot.botname+":", chat_callback)
    #plugin.add_handler(chat_regex)

    chat_regex_2=plugin.RegexHandler("@"+plugin.mroom.bot.botname, chat_callback)
    #plugin.add_handler(chat_regex_2)

    image_regex=plugin.RegexHandler("image", image_callback)
    #plugin.add_handler(image_regex)

    catchall_regex=plugin.RegexHandler(".*", callback_chooser)
    plugin.add_handler(catchall_regex)


    class thread_handler:
        def __init__(self, handle_callback):
            self.handle_callback=handle_callback
    #function to test if message is related to a message from the bot
        async def test_if_my_thread(self, room, event):
            #check if event is a reply
            if 'm.relates_to' in event.source['content'] and 'rel_type' in event.source['content']['m.relates_to'] and event.source['content']['m.relates_to']['rel_type'] == 'm.in_reply_to':
                #get the event_id of the event the message is replying to
                event_id=event.source['content']['m.relates_to']['event_id']
                #get the event
                eventrq=await plugin.client.room_get_event(room, event_id)
                #check if the sender of the event is the bot
                if eventrq.event.sender==plugin.mroom.bot.botname:
                    return True
            return False
        def test_callback(self, room, event):
            #check if event is a reply
            print("Running test_callback")
            return self.test_if_my_thread(room, event)
    #plugin.add_handler(chat_handler(chat_callback_test))








    class conversation_handler:
        def __init__(self, handle_callback):
            self.handle_callback=handle_callback
        
        def test_callback(self, room, event):
            #test if event.formatted_body has a '<mx-reply>.*</mx-reply>' in it and match the text after it
            if 'formatted_body' in event.source and re.search('<mx-reply>.*</mx-reply>', event.source['formatted_body']):
                #get the text after the reply
                text_after_reply=re.search('<mx-reply>.*</mx-reply>(.*)', event.source['formatted_body']).group(1)
                #test if the text after the reply starts with a '!'
                if text_after_reply.startswith('!'):
                    return False

            #test if keys of room.nio_room.users are only two, and one matches the botname and if the event is a message
            return len(room.nio_room.users.keys())==2 and room.nio_room.own_user_id in room.nio_room.users.keys() and [room.nio_room.users[user_id].power_level for user_id in room.nio_room.users.keys()] == [100,100] and 'type' in event.source and event.source['type']=='m.room.message' and room.nio_room.own_user_id != event.source['sender'] and not event.source['content']['body'].startswith('!')

        
    #plugin.add_handler(conversation_handler(chat_callback))

            