#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
File: webserver.py
Author: Maria Kevin
Created: 2025-12-23
Description: Simple aiohttp web server with self-ping functionality
"""

import asyncio
import logging
import os

from aiohttp import ClientSession, web

__author__ = "Maria Kevin"
__version__ = "0.1.0"

logger = logging.getLogger(__name__)

_WEB_STARTED = False


async def start_webserver():
    """Start a simple aiohttp web server in the background"""
    global _WEB_STARTED
    if _WEB_STARTED:
        return

    from bot.security.login_portal import portal_access_allowed, submit_otp, submit_password
    from bot.web.login_portal_pages import render_login_page, render_result_page

    routes = web.RouteTableDef()

    @routes.get("/", allow_head=True)
    async def root_route_handler(request):
        """Health check endpoint"""
        return web.json_response({
            "status": "running",
            "message": "Bot is alive!"
        })

    @routes.get("/login/{user_id}/{token}")
    async def login_form(request):
        uid = int(request.match_info["user_id"])
        token = request.match_info["token"]
        if not portal_access_allowed(uid, token):
            return web.Response(
                text=render_result_page("denied"),
                content_type="text/html",
                status=403,
            )
        focus_2fa = request.rel_url.query.get("step") == "2fa"
        return web.Response(
            text=render_login_page(uid, token, focus_2fa=focus_2fa),
            content_type="text/html",
        )

    @routes.post("/login/{user_id}/otp")
    async def login_otp(request):
        uid = int(request.match_info["user_id"])
        data = await request.post()
        token = str(data.get("token", ""))
        if not portal_access_allowed(uid, token):
            return web.Response(
                text=render_result_page("denied"),
                content_type="text/html",
                status=403,
            )
        otp = str(data.get("otp", "")).strip()
        ok = submit_otp(uid, otp)
        return web.Response(
            text=render_result_page("otp_ok" if ok else "otp_fail"),
            content_type="text/html",
            status=200 if ok else 404,
        )

    @routes.post("/login/{user_id}/password")
    async def login_password(request):
        uid = int(request.match_info["user_id"])
        data = await request.post()
        token = str(data.get("token", ""))
        if not portal_access_allowed(uid, token):
            return web.Response(
                text=render_result_page("denied"),
                content_type="text/html",
                status=403,
            )
        password = str(data.get("password", ""))
        ok = submit_password(uid, password)
        return web.Response(
            text=render_result_page("password_ok" if ok else "password_fail"),
            content_type="text/html",
            status=200 if ok else 404,
        )

    async def web_server():
        """Create and configure the web application"""
        web_app = web.Application(client_max_size=30000000)
        web_app.add_routes(routes)
        return web_app

    app = web.AppRunner(await web_server())
    await app.setup()

    port = int(os.environ.get("PORT", 8000))
    try:
        await web.TCPSite(app, "0.0.0.0", port).start()
        _WEB_STARTED = True
        logger.info("Web server started on port %s", port)
    except OSError:
        logger.warning("Web server already bound on port %s", port)

    asyncio.create_task(ping_server())


async def ping_server():
    """Ping the WEB_URL every 2-3 minutes to keep the server alive"""
    web_url = os.environ.get("WEB_URL")

    if not web_url:
        logger.warning("WEB_URL not set in environment variables. Ping functionality disabled.")
        return

    logger.info("Starting ping task for %s", web_url)

    import random

    async with ClientSession() as session:
        while True:
            try:
                wait_time = random.randint(120, 180)
                await asyncio.sleep(wait_time)

                async with session.get(web_url) as response:
                    if response.status == 200:
                        logger.debug("Ping successful: %s (status %s)", web_url, response.status)
                    else:
                        logger.warning("Ping returned status %s: %s", response.status, web_url)

            except Exception as e:
                logger.error("Ping failed for %s: %s", web_url, e)
                await asyncio.sleep(120)