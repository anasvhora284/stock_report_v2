# -*- coding: utf-8 -*-
from odoo import api, fields, models, _

class StockReportConfig(models.Model):
    _name = "stock.report.config"
    _description = "Stock Report Configuration"
    _order = "sequence, id"
    
    name = fields.Char(string="Name", required=True)
    attribute_ids = fields.Many2many('product.attribute', string="Attributes", required=True)
    menu_id = fields.Many2one('ir.ui.menu', string="Menu Item", readonly=True, copy=False)
    parent_menu_id = fields.Many2one('ir.ui.menu', string="Parent Menu", required=True,
                                    default=lambda self: self.env.ref('stock.menu_stock_root', raise_if_not_found=False))
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    use_forecast = fields.Boolean(string="Use Forecasted Quantities", default=False)
    filter_zero = fields.Boolean(string="Hide Zero Quantities", default=True)
    include_negative = fields.Boolean(string="Include Negative Quantities", default=True)
    action_id = fields.Many2one('ir.actions.client', string="Client Action", readonly=True, copy=False)
    
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            record._create_menu_and_action()
        return records
    
    def write(self, vals):
        result = super().write(vals)
        if any(field in vals for field in ['name', 'attribute_ids', 'parent_menu_id']):
            for record in self:
                if record.menu_id:
                    record.menu_id.unlink()
                if record.action_id:
                    record.action_id.unlink()
                record._create_menu_and_action()
        return result
    
    def unlink(self):
        for record in self:
            if record.menu_id:
                record.menu_id.unlink()
            if record.action_id:
                record.action_id.unlink()
        return super().unlink()
    
    def _create_menu_and_action(self):
        self.ensure_one()
        
        action = self.env['ir.actions.client'].create({
            'name': self.name,
            'type': 'ir.actions.client',
            'tag': 'dynamic_attribute_view',
            'context': {
                'config_id': self.id,
                'attribute_ids': self.attribute_ids.ids,
                'filter_zero': self.filter_zero,
                'include_negative': self.include_negative,
                'use_forecast': self.use_forecast,
            },
        })
        self.action_id = action.id
        
        menu = self.env['ir.ui.menu'].create({
            'name': self.name,
            'action': f'ir.actions.client,{action.id}',
            'parent_id': self.parent_menu_id.id if self.parent_menu_id else False,
            'sequence': self.sequence,
        })
        self.menu_id = menu.id
        
    @api.model
    def get_available_configs(self):
        configs = self.search([('active', '=', True)], order='sequence, name')
        return [{
            'id': config.id,
            'name': config.name,
            'attribute_ids': config.attribute_ids.ids,
            'attribute_names': config.attribute_ids.mapped('name'),
            'filter_zero': config.filter_zero,
            'include_negative': config.include_negative,
            'use_forecast': config.use_forecast,
        } for config in configs] 