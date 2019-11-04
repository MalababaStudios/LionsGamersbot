"""
The bot will be run from this file. Here the handler functions will be assigned.
"""

import logging
import handlers
import const
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Updater, CallbackQueryHandler, CommandHandler, MessageHandler, Filters,\
    PreCheckoutQueryHandler, RegexHandler

from bot_tokens import BOT_TOKEN

# Console logger
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)


def stop_bot(updater):
    logger.info("Shutting down...")
    updater.stop()
    logger.info("Done (shutdown)")


def main():
    if BOT_TOKEN == "":
        logger.error("TOKEN not defined. Put your bot token on bot_tokens.py")
        return

    updater = Updater(BOT_TOKEN)
    h = updater.dispatcher.add_handler

    const.aux.BOT_USERNAME = updater.bot.username
    handlers.NOTIFY_KEYBOARD_MARKUP = InlineKeyboardMarkup([[InlineKeyboardButton("🔔 Notificaciones",
                                                                     url="t.me/%s?start=notifications"
                                                                         % const.aux.BOT_USERNAME)]])

    # Assigning handlers
    h(CommandHandler("help", handlers.help))
    h(CommandHandler("more", handlers.more))
    h(CommandHandler("ping", handlers.ping))
    h(CommandHandler("donate", handlers.donate, pass_user_data=True))
    h(CommandHandler("support", handlers.support, filters=Filters.private))
    h(CommandHandler("support", handlers.support_group, filters=Filters.group))
    h(CommandHandler("about", handlers.about))
    h(CallbackQueryHandler(handlers.change_donation_quantity, pattern=r"don\*", pass_user_data=True))
    h(CallbackQueryHandler(handlers.send_donation_receipt, pattern=r"donate$", pass_user_data=True))
    h(MessageHandler(filters=Filters.successful_payment, callback=handlers.completed_donation))
    h(PreCheckoutQueryHandler(handlers.approve_transaction))
    h(CommandHandler("ts3", handlers.ts3_command))
    h(CommandHandler("discord", handlers.discord_command))
    h(RegexHandler(r"/start notifications", handlers.ts3_notifications_panel))
    h(CommandHandler("start", handlers.start))
    h(CallbackQueryHandler(handlers.ts3_notifications_manage, pattern=r"notify_[activate|deactivate]"))
    h(CommandHandler("/campaigns", handlers.admin_campaigns))
    h(CommandHandler("/new_campaign", handlers.admin_new_campaign))
    h(CommandHandler("/end_campaign", handlers.admin_end_campaign))
    h(CommandHandler("/send_campaign", handlers.admin_send_campaign))
    h(CommandHandler("/donors", handlers.admin_donors))
    h(CommandHandler("/now_donation", handlers.admin_new_donation))
    h(MessageHandler(Filters.status_update.new_chat_members, handlers.check_group_authorized))

    updater.dispatcher.add_error_handler(handlers.error)

    updater.dispatcher.job_queue.run_repeating(handlers.notify_new_connections, 300, 0)

    updater.start_polling()

    # CONSOLE
    while True:
        inp = input("")
        if inp:
            input_c = inp.split()[0]
            args = inp.split()[1:]
            strig = ""
            for e in args:
                strig = strig + " " + e

            if input_c == "stop":
                stop_bot(updater)
                break

            else:
                print("Unknown command")


if __name__ == '__main__':
    main()
