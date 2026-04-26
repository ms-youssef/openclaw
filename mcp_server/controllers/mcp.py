# -*- coding: utf-8 -*-
import json
import logging

import werkzeug.exceptions

from odoo import http, release
from odoo.exceptions import AccessDenied, AccessError, UserError, ValidationError
from odoo.http import Response, request

_logger = logging.getLogger(__name__)

MODULE_VERSION = '1.0'


def _json_response(payload, status=200):
    return Response(
        json.dumps(payload, default=str),
        status=status,
        content_type='application/json',
    )


def _error(status, code, message):
    return _json_response({'error': code, 'message': message}, status=status)


class MCPController(http.Controller):

    # ------------------------------------------------------------------
    # Auth + dispatch helpers
    # ------------------------------------------------------------------

    def _authenticate(self):
        auth = request.httprequest.headers.get('Authorization', '')
        if not auth or not auth.lower().startswith('bearer '):
            raise werkzeug.exceptions.Unauthorized()
        key = auth[7:].strip()
        if not key:
            raise werkzeug.exceptions.Unauthorized()
        try:
            user_id = request.env['res.users.apikeys']._check_credentials(
                scope='rpc', key=key,
            )
        except (AccessDenied, AccessError):
            raise werkzeug.exceptions.Unauthorized()
        if not user_id:
            raise werkzeug.exceptions.Unauthorized()
        return request.env(user=user_id, su=False)

    def _resolve_model(self, env, model_name):
        config = env['mcp.enabled.model'].sudo()._resolve(model_name)
        if not config:
            raise werkzeug.exceptions.NotFound()
        # Re-bind to the user-scoped env so subsequent reads honor ACLs
        return config.with_env(env)

    def _read_json(self):
        try:
            raw = request.httprequest.get_data(as_text=True) or '{}'
            return json.loads(raw)
        except (TypeError, ValueError):
            raise UserError("Request body must be valid JSON.")

    def _wrap(self, fn):
        try:
            return fn()
        except werkzeug.exceptions.HTTPException:
            raise
        except (AccessError, AccessDenied) as exc:
            return _error(403, 'access_denied', str(exc) or "Access denied.")
        except (UserError, ValidationError) as exc:
            message = getattr(exc, 'args', None) and exc.args[0] or str(exc)
            return _error(400, 'validation', str(message))
        except Exception:
            _logger.exception("MCP controller failure")
            return _error(500, 'internal', "Internal server error.")

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    @http.route('/mcp/health', type='http', auth='none',
                methods=['GET'], csrf=False, save_session=False)
    def health(self, **kwargs):
        def run():
            self._authenticate()
            return _json_response({
                'status': 'ok',
                'odoo_version': release.version,
                'module_version': MODULE_VERSION,
            })
        return self._wrap(run)

    @http.route('/mcp/models', type='http', auth='none',
                methods=['GET'], csrf=False, save_session=False)
    def list_models(self, **kwargs):
        def run():
            env = self._authenticate()
            configs = env['mcp.enabled.model'].search([])
            payload = []
            for cfg in configs:
                payload.append({
                    'model': cfg.model_name,
                    'name': cfg.model_id.name,
                    'description': cfg.description or '',
                    'operations': {
                        'search': cfg.allow_search,
                        'read': cfg.allow_read,
                        'create': cfg.allow_create,
                        'write': cfg.allow_write,
                        'unlink': cfg.allow_unlink,
                    },
                    'fields': cfg._allowed_field_names(),
                })
            return _json_response({'models': payload})
        return self._wrap(run)

    @http.route('/mcp/<string:model>/fields', type='http', auth='none',
                methods=['GET'], csrf=False, save_session=False)
    def fields(self, model, **kwargs):
        def run():
            env = self._authenticate()
            cfg = self._resolve_model(env, model)
            cfg._check_operation('read')
            allowed = cfg._allowed_field_names()
            attributes = ['type', 'string', 'help', 'selection',
                          'required', 'readonly', 'relation']
            info = env[cfg.model_name].fields_get(allowed, attributes)
            return _json_response({
                'model': cfg.model_name,
                'description': cfg.description or '',
                'fields': info,
            })
        return self._wrap(run)

    @http.route('/mcp/<string:model>/search_read', type='http', auth='none',
                methods=['POST'], csrf=False, save_session=False)
    def search_read(self, model, **kwargs):
        def run():
            env = self._authenticate()
            cfg = self._resolve_model(env, model)
            cfg._check_operation('search')
            cfg._check_operation('read')
            body = self._read_json()
            domain = body.get('domain') or []
            fields = cfg._filter_fields(body.get('fields'))
            limit = body.get('limit')
            offset = body.get('offset') or 0
            order = body.get('order')
            records = env[cfg.model_name].search_read(
                domain=domain,
                fields=fields,
                offset=offset,
                limit=limit,
                order=order,
            )
            return _json_response({'records': records})
        return self._wrap(run)

    @http.route('/mcp/<string:model>/read', type='http', auth='none',
                methods=['POST'], csrf=False, save_session=False)
    def read(self, model, **kwargs):
        def run():
            env = self._authenticate()
            cfg = self._resolve_model(env, model)
            cfg._check_operation('read')
            body = self._read_json()
            ids = body.get('ids') or []
            if not isinstance(ids, list):
                raise UserError("`ids` must be a list of integers.")
            fields = cfg._filter_fields(body.get('fields'))
            records = env[cfg.model_name].browse(ids).read(fields)
            return _json_response({'records': records})
        return self._wrap(run)

    @http.route('/mcp/<string:model>/create', type='http', auth='none',
                methods=['POST'], csrf=False, save_session=False)
    def create(self, model, **kwargs):
        def run():
            env = self._authenticate()
            cfg = self._resolve_model(env, model)
            cfg._check_operation('create')
            body = self._read_json()
            values = cfg._filter_values(body.get('values') or {})
            record = env[cfg.model_name].create(values)
            return _json_response({'id': record.id})
        return self._wrap(run)

    @http.route('/mcp/<string:model>/write', type='http', auth='none',
                methods=['POST'], csrf=False, save_session=False)
    def write(self, model, **kwargs):
        def run():
            env = self._authenticate()
            cfg = self._resolve_model(env, model)
            cfg._check_operation('write')
            body = self._read_json()
            ids = body.get('ids') or []
            if not isinstance(ids, list):
                raise UserError("`ids` must be a list of integers.")
            values = cfg._filter_values(body.get('values') or {})
            env[cfg.model_name].browse(ids).write(values)
            return _json_response({'success': True})
        return self._wrap(run)

    @http.route('/mcp/<string:model>/unlink', type='http', auth='none',
                methods=['POST'], csrf=False, save_session=False)
    def unlink(self, model, **kwargs):
        def run():
            env = self._authenticate()
            cfg = self._resolve_model(env, model)
            cfg._check_operation('unlink')
            body = self._read_json()
            ids = body.get('ids') or []
            if not isinstance(ids, list):
                raise UserError("`ids` must be a list of integers.")
            env[cfg.model_name].browse(ids).unlink()
            return _json_response({'success': True})
        return self._wrap(run)
