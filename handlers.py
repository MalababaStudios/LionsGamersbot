"""
Here should be declared all functions that handle the supported Telegram API calls.
"""

import const
import bot_tokens
import json
import telnetlib
import requests
import database
import logging
import pprint as pp
from bot_tokens import PAYMENT_PROVIDER_TOKEN
from lang import get_lang
from telegram import ParseMode, InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice
from telegram.error import BadRequest

NOTIFY_KEYBOARD_MARKUP = InlineKeyboardMarkup([[InlineKeyboardButton("🔔 Notificaciones",
                                                                     url="t.me/%s?start=notifications"
                                                                         % const.aux.BOT_USERNAME)]])

logger = logging.getLogger(__name__)
ts3_connections = []


def generic_message(bot, update, text_code, **kwargs):
    """Answers the message with a fixed text. Add kwargs to insert text."""
    message = update.effective_message
    lang = get_lang(update.effective_user.language_code)

    message.reply_text(lang.get_text(text_code, **kwargs), parse_mode=ParseMode.MARKDOWN)


def start(bot, update):
    generic_message(bot, update, "start")


def help(bot, update):
    generic_message(bot, update, "help")


def more(bot, update):
    generic_message(bot, update, "more")


def about(bot, update):
    generic_message(bot, update, "about", **{"botusername": bot.username, "version": const.VERSION})


def ping(bot, update):
    update.effective_message.reply_text("Pong!", quote=False)


def donate(bot, update, user_data):
    if PAYMENT_PROVIDER_TOKEN is None:
        generic_message(bot, update, "donations_not_available")
        return

    lang = get_lang(update.effective_user.language_code)

    user_data["donation"] = 5
    text = lang.get_text("donate")
    keyboard = [[InlineKeyboardButton("❤ %s€ ❤" % user_data["donation"], callback_data="donate")],
                [InlineKeyboardButton("⏬", callback_data="don*LLL"),
                 InlineKeyboardButton("⬇️", callback_data="don*LL"),
                 InlineKeyboardButton("🔽", callback_data="don*L"),
                 InlineKeyboardButton("🔼", callback_data="don*G"),
                 InlineKeyboardButton("⬆️", callback_data="don*GG"),
                 InlineKeyboardButton("⏫", callback_data="don*GGG")]]
    update.message.reply_text(text,
                              reply_markup=InlineKeyboardMarkup(keyboard),
                              parse_mode=ParseMode.MARKDOWN,
                              disable_web_page_preview=True)


def change_donation_quantity(bot, update, user_data):

    if "donation" not in user_data:
        user_data["donation"] = 5

    s = update.callback_query.data.split("*")
    change = 5 ** (s[1].count("G") - 1) if "G" in s[1] else -(5 ** (s[1].count("L") - 1))
    user_data["donation"] += change
    if user_data["donation"] < 1:
        user_data["donation"] = 1

    keyboard = [[InlineKeyboardButton("❤ %s€ ❤" % user_data["donation"], callback_data="donate")],
                [InlineKeyboardButton("⏬", callback_data="don*LLL"),
                 InlineKeyboardButton("⬇️", callback_data="don*LL"),
                 InlineKeyboardButton("🔽", callback_data="don*L"),
                 InlineKeyboardButton("🔼", callback_data="don*G"),
                 InlineKeyboardButton("⬆️", callback_data="don*GG"),
                 InlineKeyboardButton("⏫", callback_data="don*GGG")]]

    update.effective_message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
    update.callback_query.answer()


def send_donation_receipt(bot, update, user_data):
    lang = get_lang(update.effective_user.language_code)

    if "donation" not in user_data:
        user_data["donation"] = 5

    title = lang.get_text("donation_title")
    description = lang.get_text("donation_description")
    prices = [LabeledPrice(title, user_data["donation"] * 100)]

    bot.send_invoice(chat_id=update.effective_chat.id,
                     title=title,
                     description=description,
                     payload="approve_donation",
                     provider_token=PAYMENT_PROVIDER_TOKEN,
                     start_parameter="donacion",
                     currency="EUR",
                     prices=prices)
    update.effective_message.edit_reply_markup(reply_markup=InlineKeyboardMarkup([[]]))


def approve_transaction(bot, update):
    query = update.pre_checkout_query

    if query.invoice_payload != 'approve_donation':
        bot.answer_pre_checkout_query(pre_checkout_query_id=query.id, ok=False,
                                      error_message="Algo ha fallado, vuelve a intentarlo por favor.")
    else:
        bot.answer_pre_checkout_query(pre_checkout_query_id=query.id, ok=True)


def completed_donation(bot, update):
    update.effective_message.reply_text("Muchisimas gracias por donar!! ❤️❤️❤️")
    bot.send_message(const.ADMIN_TELEGRAM_ID, "%s ha donado!" % update.effective_user)


def support(bot, update):
    message = update.effective_message
    lang = get_lang(update.effective_user.language_code)

    if len(message.text.replace("/support", "")) > 0:
        message.forward(const.ADMIN_TELEGRAM_ID)
        message.reply_text(lang.get_text("support_sent"))
    else:
        message.reply_text(lang.get_text("support_default"))


def support_group(bot, update):
    generic_message(bot, update, "private_command")


def error(bot, update, error):
    bot.send_message(const.ADMIN_TELEGRAM_ID, "The update:\n%s\nhas caused this error:\n%s" % (str(update), str(error)))


def _parse_telnet_data(data):

    user_list = data.replace(b"error id=0 msg=ok", b"").split(b"|")
    parsed = []

    for user in user_list:
        new = {}
        parameters = user.split()
        for parameter in parameters:
            s = parameter.split(b"=")
            if len(s) > 1:
                s[1] = s[1].replace(b"\\s", b" ")
                s[1] = s[1].replace(b"\\p", b"|")
                new[s[0]] = s[1]
            else:
                new[s[0]] = None
        if b"client_nickname" in new and b"vetutest" in new[b"client_nickname"]:
            continue
        parsed.append(new)

    logger.debug("PARSED DATA:" + str(parsed))
    return parsed


def _server_group_to_text(serverg_list):
    server_group_to_emoji = {6: "👑", 8: "💩", 7: "🐶", 9: "👮", 10: "🦁", 11: "❤️"}
    text = ""
    s = serverg_list.split(b",")
    serverg_list = map(int, s)

    for grupo in serverg_list:
        text += server_group_to_emoji[grupo]
    return text


def _get_ts3_info(get_channels=False):
    conexiones = []

    tn = telnetlib.Telnet(bot_tokens.TS3_QUERY_ADDRESS, 10011)

    tn.read_until(b"command.\n", 5)
    tn.write(b"login %s %s\n" % (bot_tokens.TS3_QUERY_USER, bot_tokens.TS3_QUERY_PASSWORD))
    tn.read_until(b"error id=0 msg=ok\n", 5)
    tn.write(b"use 1\n")
    tn.read_until(b"error id=0 msg=ok\n", 5)
    tn.write(b"clientlist\n")
    data = tn.read_until(b"error id=0 msg=ok\n", 5)

    clients = _parse_telnet_data(data)
    channels_in_use = set()

    for client in clients:
        channels_in_use.add(client[b"cid"])
        tn.write(b"clientinfo clid=%s\n" % client[b"clid"])
        data = tn.read_until(b"error id=0 msg=ok\n", 5)
        client.update(_parse_telnet_data(data)[0])
        conexiones.append((client[b"client_database_id"], client[b"client_nickname"]))

    if get_channels:
        data = b""
        for cid in channels_in_use:
            tn.write(b"channelinfo cid=%s\n" % cid)
            if data:
                data += b"|"
            data += b"cid=%s " % cid
            data += tn.read_until(b"error id=0 msg=ok\n", 5)
        logger.debug("CHANNELS TO BE PARSED:\n" + str(data))
        channels_in_use = _parse_telnet_data(data)

    tn.write(b"logout\n")
    tn.close()

    return [clients, channels_in_use] if get_channels else clients


def notify_new_connections(bot, job=None, clients=None):

    if clients is None:
        clients = _get_ts3_info(get_channels=False)

    new = check_new_connections(clients)

    # If there is no new connections, there's nothing to do
    if not new:
        return

    if len(new) == 1:
        text = "Se ha conectado: "
    else:
        text = "Se han conectado: "

    for f in new:
        text = text.replace("{1}", "{2}").replace("{0}", "{1}")
        text += "%s{0}" % f[1].decode("utf-8")
    text = text.format(".", " y ", ", ")

    conn = database.database.get_connection()
    r = conn.execute("SELECT * FROM user_ts3_notifications_subscriptions")
    notify = [x[0] for x in r.fetchall()]

    logger.info("Notifying %s users of %s new connections" % (len(notify), len(new)))

    for user_id in notify:
        try:
            bot.send_message(user_id, text, reply_markup=NOTIFY_KEYBOARD_MARKUP)
        except BadRequest:
            pass


def check_new_connections(clients):
    global ts3_connections
    tmp = [(c[b"client_database_id"], c[b"client_nickname"]) for c in clients]

    new = set(tmp) - set(ts3_connections)
    ts3_connections = list(tmp)

    return new


def discord_command(bot, update):
    trad = {"idle": "Ausente",
            "online": "En linea",
            "dnd": "No molestar"}
    text = ""
    jj = json.loads(requests.get(bot_tokens.DISCORD_PANEL_URL).content)

    for member in jj["members"]:
        if member["status"] != "dnd":
            text += "*%s* - %s\n" % (member["username"],
                                   member["game"]["name"] if "game" in member else trad[member["status"]])

    if not text:
        text += "*No hay nadie conectado*\n"

    text = "*%s*\n\n" % jj["name"] + text + "\n*Link* %s" % jj["instant_invite"]

    update.effective_message.reply_text(text=text,
                                        parse_mode="Markdown",
                                        disable_web_page_preview=True,
                                        quote=False)


def ts3_command(bot, update):

    clients, channels_in_use = _get_ts3_info(get_channels=True)

    if clients:
        text = "*Actualmente conectados:\n\n*"

        for channel in channels_in_use:
            text += "*%s*\n" % channel[b"channel_name"].decode("utf-8")
            for client in clients:
                if client[b"cid"] == channel[b"cid"]:
                    text = text.replace("{0}", "{1}")

                    text += "{0} %s - %s\n" % (client[b"client_nickname"].decode("utf-8"),
                                               _server_group_to_text(client[b"client_servergroups"]))
            text = text.format("└", "├") + "\n"

        notify_new_connections(bot, clients=clients)
    else:
        text = "No hay nadie conectado a ts3 en estos momentos :c"

    update.effective_message.reply_text(text,
                                        parse_mode="Markdown",
                                        quote=False,
                                        reply_markup=NOTIFY_KEYBOARD_MARKUP)


def ts3_notifications_panel(bot, update):
    """A panel on the private chat to activate/deactivate the ts3 notifications."""

    lang = get_lang(update.effective_user.language_code)

    keyboard = [[InlineKeyboardButton("🔔", callback_data="notify_activate"),
                 InlineKeyboardButton("🔕", callback_data="notify_deactivate")]]

    update.effective_message.reply_text(lang.get_text("notifications_panel"),
                                        reply_markup=InlineKeyboardMarkup(keyboard))


def ts3_notifications_manage(bot, update):
    """Response to the notifications_panel buttons"""
    conn = database.database.get_connection()

    if update.callback_query.data == "notify_activate":
        r = conn.execute("SELECT * FROM user_ts3_notifications_subscriptions WHERE id=?", [update.effective_user.id])

        # Check if the user is already in the database
        if not r.fetchone():
            conn.execute("INSERT INTO user_ts3_notifications_subscriptions VALUES (?)", [update.effective_user.id])
            conn.commit()

        update.callback_query.answer("🔔 Notificaciones activadas")
    else:
        conn.execute("DELETE FROM user_ts3_notifications_subscriptions WHERE id=?", [update.effective_user.id])
        conn.commit()

        update.callback_query.answer("🔕 Notificaciones desactivadas")

    conn.close()


def _check_admin_id(update):
    if update.effective_user.id != const.ADMIN_TELEGRAM_ID:
        logger.warning("UNAUTHORIZED ADMIN COMMAND BY ORDER OF: %s" % str(update.effective_user))
        return False
    return True


def admin_help(bot, update):

    if not _check_admin_id(update):
        return

    commands = """/campaigns
    /new_campaign (message txt, objective int, repeat (y/N))
    /end_campaign (id)
    /send_campaign (id, pin (S/n))
    /donors
    /new_donation (nick txt, amount float)
    """

    update.effective_message.reply_text()


def admin_campaigns(bot, update):

    if not _check_admin_id(update):
        return

    conn = database.database.get_connection()

    c = conn.execute("SELECT * FROM donation_campaigns")
    result = database.database.get_all_fetched_as_dict(c)

    update.effective_message.reply_text(pp.pformat(result, 2))

    conn.close()


def admin_new_campaign(bot, update):

    if not _check_admin_id(update):
        return

    args = update.effective_message.text.replace("/new_campaigns ", "").split("\n")

    if args < 2 or args > 3:
        update.effective_message.reply_text("Bad arguments")
        return

    if len(args) == 2:
        args.append(False)
    else:
        if args[2].lower() == "y":
            args[2] = True
        elif args[2].lower() == "n":
            args[2] = False
        else:
            update.effective_message.reply_text("Bad arguments")
            return

    conn = database.database.get_connection()

    sql = "INSERT INTO donation_campaigns (message, objective, progress, repeat_monthly) VALUES (?, ?, ?, ?)"
    conn.execute(sql, args)
    conn.commit()
    conn.close()

    update.effective_message.reply_text("Success?")


def admin_end_campaign(bot, update):

    if not _check_admin_id(update):
        return

    args = update.effective_message.text.replace("/new_campaigns ", "").split("\n")

    if len(args) < 1:
        update.effective_message.reply_text("Bad arguments")
        return

    conn = database.database.get_connection()

    conn.execute("DELETE FROM donation_campaigns WHERE id=?", [args[0]])
    conn.commit()
    conn.close()

    update.effective_message.reply_text("Success?")


def admin_send_campaign(bot, update):

    if not _check_admin_id(update):
        return

    args = update.effective_message.text.replace("/send_campaign ", "").split("\n")

    if len(args) < 1 or len(args) > 2:
        update.effective_message.reply_text("Bad arguments")
        return

    if len(args) == 1:
        args.append(True)
    elif len(args) > 1:
        if args[1].lower() == "y":
            args[1] = True
        elif args[1].lower() == "n":
            args[1] = False
        else:
            update.effective_message.reply_text("Bad arguments")
            return

    conn = database.database.get_connection()

    c = conn.execute("SELECT * FROM donation_campaigns WHERE id=?", [args[0]])
    campaign_info = database.database.get_one_fetched_as_dict(c)
    c = conn.execute("SELECT nick FROM donors LIMIT 5 ORDER BY amount DESC")
    conn.close()
    top_5_donors = database.database.get_all_fetched_as_dict(c)
    top_5_donors = [x["nick"] for x in top_5_donors]
    
    text = """*{campaign_message}*
    *Objetivo:* {campaign_objective}€
    *Progreso:* {progress_symbol}{campaign_progress}€
    La campaña termina a al finalizar el mes.
    
    *TOP 5 DONADORES* (desde el comienzo de los tiempos)
    1. {0}
    2. {1}
    3. {2}
    4. {3}
    5. {4}
    
    Puedes donar en paypal.me/vetu11
    """.format(*top_5_donors,
               campaign_message=campaign_info["message"],
               campaign_objective=campaign_info["objective"],
               progress_symbol="❌" if campaign_info["progress"] < campaign_info["objective"] else "✅",
               campaign_progress=campaign_info["progress"])

    message = update.effective_message.reply_text(text,
                                                           parse_mode=ParseMode.MARKDOWN)

    # Do we have to pin it?
    if args[1]:
        bot.pin_chat_message(message.message_id, message.chat_id)


def admin_donors(bot, update):

    if not _check_admin_id(update):
        return

    conn = database.database.get_connection()

    c = conn.execute("SELECT * FROM donors")
    result = database.database.get_all_fetched_as_dict(c)

    update.effective_message.reply_text(pp.pformat(result, 2))

    conn.close()


def admin_new_donation(bot, update):

    if not _check_admin_id(update):
        return

    args = update.effective_message.text.replace("/new_donation ", "").split("\n")

    if len(args) < 1 or len(args) > 1:
        update.effective_message.reply_text("Bad arguments")
        return

    conn = database.database.get_connection()

    c = conn.execute("SELECT * FROM donors WHERE nick=?", [args[0]])
    user_info = database.database.get_one_fetched_as_dict(c)

    if not user_info:
        conn.execute("INSERT INTO donors VALUES (?, ?)", args)
    else:
        conn.execute("UPDATE donors SET amount=? WHERE nick=?", [args[1] + user_info["amount"], args[0]])
    conn.commit()
    conn.close()

    text = "*%s acaba de donar %s€!* Contribuye con tu capital en paypal.me/vetu11" % args

    for group_id in bot_tokens.AUTHORIZED_GROUPS:
        bot.send_message(chat_id=group_id,
                         text=text,
                         parse_mode=ParseMode.MARKDOWN)


def check_group_authorized(bot, update):
    if update.effective_chat.id not in bot_tokens.AUTHORIZED_GROUPS:
        update.effective_message.reply_text("UNAUTHORIZED GROUP: %s" % update.effective_chat.id)
        bot.leave_chat(update.effective_chat.id)
