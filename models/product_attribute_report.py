# -*- coding: utf-8 -*-
from odoo import api, models, fields, tools, _
import logging
from odoo.exceptions import UserError
from collections import defaultdict

_logger = logging.getLogger(__name__)

class ProductAttributeReport(models.Model):
    _name = 'product.attribute.report'
    _description = 'Product Attribute Report'
    _auto = False  # Don't create database table
    _rec_name = 'product_name'
    _order = 'product_name, attribute_name'
    
    # Fields for SQL view
    id = fields.Integer(readonly=True)
    product_id = fields.Many2one('product.product', string='Product Variant', readonly=True)
    product_tmpl_id = fields.Many2one('product.template', string='Product Template', readonly=True)
    product_name = fields.Char(string='Product Name', readonly=True)
    default_code = fields.Char(string='Internal Reference', readonly=True)
    attribute_id = fields.Many2one('product.attribute', string='Attribute', readonly=True)
    attribute_name = fields.Char(string='Attribute Name', readonly=True)
    attribute_value_id = fields.Many2one('product.attribute.value', string='Attribute Value', readonly=True)
    attribute_value = fields.Char(string='Attribute Value', readonly=True)
    qty_available = fields.Float(string='Quantity On Hand', readonly=True, digits='Product Unit of Measure')
    virtual_available = fields.Float(string='Forecast Quantity', readonly=True, digits='Product Unit of Measure')
    incoming_qty = fields.Float(string='Incoming', readonly=True, digits='Product Unit of Measure')
    outgoing_qty = fields.Float(string='Outgoing', readonly=True, digits='Product Unit of Measure')
    reserved_qty = fields.Float(string='Reserved', readonly=True, digits='Product Unit of Measure')
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure', readonly=True)
    
    def init(self):
        """Initialize SQL view for the report"""
        # First drop the view if it exists
        tools.drop_view_if_exists(self.env.cr, self._table)
        
        # Also try to drop the table if it exists
        self.env.cr.execute("DROP TABLE IF EXISTS %s CASCADE" % self._table)
        
        # Create SQL view that joins product, attributes and stock data
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                WITH stock_data AS (
                    SELECT 
                        sq.product_id,
                        SUM(sq.quantity) as qty_available,
                        SUM(sq.reserved_quantity) as reserved_qty
                    FROM stock_quant sq
                    JOIN stock_location sl ON sq.location_id = sl.id
                    WHERE sl.usage = 'internal'
                    GROUP BY sq.product_id
                )
                
                SELECT
                    ROW_NUMBER() OVER() AS id,
                    pp.id AS product_id,
                    pt.id AS product_tmpl_id,
                    pt.name AS product_name,
                    pp.default_code AS default_code,
                    pa.id AS attribute_id,
                    pa.name AS attribute_name,
                    pav.id AS attribute_value_id,
                    pav.name AS attribute_value,
                    COALESCE(sd.qty_available, 0) AS qty_available,
                    0.0 AS virtual_available,
                    0.0 AS incoming_qty, 
                    0.0 AS outgoing_qty,
                    COALESCE(sd.reserved_qty, 0) AS reserved_qty,
                    pt.uom_id AS uom_id
                FROM product_product pp
                JOIN product_template pt ON pp.product_tmpl_id = pt.id
                LEFT JOIN product_template_attribute_value ptav ON ptav.product_tmpl_id = pt.id
                LEFT JOIN product_attribute_value pav ON ptav.product_attribute_value_id = pav.id
                LEFT JOIN product_attribute pa ON pav.attribute_id = pa.id
                LEFT JOIN stock_data sd ON pp.id = sd.product_id
                WHERE pt.active = true AND pt.type = 'product'
            )
        """ % self._table)

    @api.model
    def get_attribute_data(self, options=None):
        """
        Main method to get product variants with attributes & stock quantities
        :param options: dictionary with configuration options
            - attribute_ids: list of attribute IDs to filter on
            - filter_zero: boolean to filter out zero quantities
            - include_negative: boolean to include negative quantities
            - use_forecast: boolean to use forecasted quantity instead of on-hand
        :return: dictionary with products, variants, and attributes data
        """
        if not options:
            options = {}
        
        attribute_ids = options.get('attribute_ids', [])
        filter_zero = options.get('filter_zero', False)
        include_negative = options.get('include_negative', True)
        use_forecast = options.get('use_forecast', False)
        
        # Get attribute information
        attributes = self.env['product.attribute'].browse(attribute_ids or [])
        if not attributes and not attribute_ids:
            attributes = self.env['product.attribute'].search([], limit=10)  # Default to top 10 attributes

        # Build domain for finding products with these attributes
        domain = [('type', '=', 'product'), ('active', '=', True)]
        if attribute_ids:
            # Find templates with these attributes
            templates = self.env['product.template.attribute.value'].search(
                [('attribute_id', 'in', attribute_ids)]
            ).mapped('product_tmpl_id')
            if templates:
                domain.append(('product_tmpl_id', 'in', templates.ids))
        
        # Find variants
        products = self.env['product.product'].search(domain)
        if not products:
            return {'products': [], 'variants': [], 'attributes': self._prepare_attribute_data(attributes)}
        
        # Read product data efficiently
        fields_to_read = ['id', 'name', 'default_code', 'qty_available', 'virtual_available', 
                          'incoming_qty', 'outgoing_qty', 'uom_id', 'uom_name', 'product_tmpl_id', 'image_1920']
        product_data = products.read(fields_to_read)
        
        # Add image URLs and calculate reserved quantity
        for product in product_data:
            product['image_url'] = f'/web/image/product.product/{product["id"]}/image_1920'
            product['reserved_quantity'] = product['qty_available'] - (product['virtual_available'] - product['incoming_qty'])
        
        # Filter quantities if needed
        qty_field = 'virtual_available' if use_forecast else 'qty_available'
        if filter_zero:
            product_data = [p for p in product_data if p[qty_field] != 0]
        if not include_negative:
            product_data = [p for p in product_data if p[qty_field] >= 0]
            
        # Get attribute values for all products
        variants = []
        for product in product_data:
            # Get attribute values for this product using ORM
            product_obj = self.env['product.product'].browse(product['id'])
            attributes_data = {}
            
            # Map attribute values
            for ptav in product_obj.product_template_attribute_value_ids:
                if ptav.attribute_id.id in (attribute_ids or attributes.ids):
                    attributes_data[ptav.attribute_id.id] = ptav.product_attribute_value_id.id
            
            # Use appropriate quantity based on settings
            main_qty = product['virtual_available'] if use_forecast else product['qty_available']
            
            variants.append({
                'id': product['id'],
                'product_id': product['id'],
                'product_tmpl_id': product['product_tmpl_id'][0] if isinstance(product['product_tmpl_id'], tuple) else product['product_tmpl_id'],
                'name': product['name'],
                'default_code': product['default_code'],
                'qty': main_qty,
                'qty_on_hand': product['qty_available'],
                'qty_available': product['virtual_available'],
                'qty_incoming': product['incoming_qty'],
                'qty_outgoing': product.get('outgoing_qty', 0.0),
                'qty_reserved': product['reserved_quantity'],
                'uom_id': product['uom_id'][0] if isinstance(product['uom_id'], tuple) else product['uom_id'],
                'uom_name': product['uom_name'],
                'product_url': f'/web#id={product["id"]}&model=product.product&view_type=form',
                'image_url': f'/web/image/product.product/{product["id"]}/image_1920',
                'attributes': attributes_data
            })
            
        return {
            'products': product_data,
            'variants': variants,
            'attributes': self._prepare_attribute_data(attributes)
        }
    
    @api.model
    def get_report_data_by_config(self, config_id):
        """Get report data based on configuration ID, structured for matrix view"""
        if not config_id:
            return {'error': 'No configuration ID provided'}
            
        config = self.env['stock.report.config'].browse(config_id)
        if not config:
            return {'error': 'Configuration not found'}
            
        options = {
            'attribute_ids': config.attribute_ids.ids,
            'filter_zero': config.filter_zero,
            'include_negative': config.include_negative,
            'use_forecast': config.use_forecast,
        }
        
        # Get regular data first
        data = self.get_attribute_data(options)
        
        # Group variants by product template
        templates = {}
        template_variants = defaultdict(list)
        
        for variant in data['variants']:
            template_id = variant['product_tmpl_id']
            if template_id not in templates:
                # Get template data
                template = self.env['product.template'].browse(template_id)
                templates[template_id] = {
                    'id': template_id,
                    'name': template.name,
                    'image': f'/web/image/product.template/{template_id}/image_1920',
                    'product_url': f'/web#id={template_id}&model=product.template&view_type=form',
                    'attributes': {},
                    'variants': []
                }
                
            # Add variant to template's variants
            template_variants[template_id].append(variant)
        
        # Create matrix data structure
        result = {
            'attributes': data['attributes'],
            'products': []
        }
        
        # For each template, create a product entry with matrix data
        for template_id, template_data in templates.items():
            variants = template_variants[template_id]
            template_attributes = {}
            
            # Get template attribute configuration
            template_obj = self.env['product.template'].browse(template_id)
            attribute_lines = template_obj.attribute_line_ids
            
            # Extract attribute information
            for line in attribute_lines:
                if line.attribute_id.id in config.attribute_ids.ids:
                    template_attributes[line.attribute_id.id] = {
                        'id': line.attribute_id.id,
                        'name': line.attribute_id.name,
                        'values': [{
                            'id': value.id,
                            'name': value.name,
                            'html_color': value.html_color
                        } for value in line.value_ids]
                    }
            
            product_data = {
                'id': template_id,
                'name': template_data['name'],
                'image_url': template_data['image'],
                'product_url': template_data['product_url'],
                'variants': variants,
                'template_attributes': template_attributes
            }
            
            result['products'].append(product_data)
        
        return result
        
    def _prepare_attribute_data(self, attributes):
        """Prepare attribute data including values for frontend"""
        result = []
        for attribute in attributes:
            values = []
            for value in attribute.value_ids:
                values.append({
                    'id': value.id,
                    'name': value.name,
                    'display_name': value.display_name or value.name,
                    'html_color': value.html_color or None,
                })
            result.append({
                'id': attribute.id,
                'name': attribute.name,
                'display_type': attribute.display_type,
                'values': values,
            })
        return result
        
    @api.model
    def get_attribute_matrix(self, template_id, attribute_ids=None):
        """Get product attributes in a matrix format for templates with multiple attributes"""
        product_tmpl = self.env['product.template'].browse(template_id)
        if not product_tmpl:
            return {'error': 'Product template not found'}
            
        attribute_lines = product_tmpl.attribute_line_ids
        if not attribute_lines:
            return {'error': 'Product has no attributes'}
            
        # Get all attributes for this template
        attributes = attribute_lines.mapped('attribute_id')
        
        # If attribute_ids is specified, filter to only those attributes
        if attribute_ids:
            attributes = attributes.filtered(lambda a: a.id in attribute_ids)
            
        if len(attributes) < 1:
            return {'error': 'No valid attributes found for this product'}
            
        # Get all combinations of attributes
        matrix = {
            'template': {
                'id': product_tmpl.id,
                'name': product_tmpl.name,
                'default_code': product_tmpl.default_code,
                'image_url': f'/web/image/product.template/{product_tmpl.id}/image_1024',
            },
            'attributes': [],
            'variants': [],
        }
        
        # Add attribute data
        for attribute in attributes:
            attr_line = attribute_lines.filtered(lambda l: l.attribute_id.id == attribute.id)
            values = []
            for value in attr_line.value_ids:
                values.append({
                    'id': value.id,
                    'name': value.name,
                    'html_color': value.html_color or None,
                })
            matrix['attributes'].append({
                'id': attribute.id,
                'name': attribute.name,
                'display_type': attribute.display_type,
                'values': values,
            })
        
        # Add variant data with corresponding attribute values and quantities
        for variant in product_tmpl.product_variant_ids:
            variant_data = {
                'id': variant.id,
                'name': variant.name,
                'default_code': variant.default_code,
                'qty_available': variant.qty_available,
                'virtual_available': variant.virtual_available,
                'incoming_qty': variant.incoming_qty,
                'outgoing_qty': variant.outgoing_qty,
                'reserved_qty': variant.qty_available - (variant.virtual_available - variant.incoming_qty),
                'image_url': f'/web/image/product.product/{variant.id}/image_1024',
                'attribute_values': {},
            }
            
            # Add attribute values for this variant
            for ptav in variant.product_template_attribute_value_ids:
                if ptav.attribute_id.id in attributes.ids:
                    variant_data['attribute_values'][ptav.attribute_id.id] = {
                        'id': ptav.product_attribute_value_id.id,
                        'name': ptav.product_attribute_value_id.name,
                    }
            
            matrix['variants'].append(variant_data)
        
        return matrix 