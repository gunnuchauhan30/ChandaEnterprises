"""
FIFO Stock Management Service
Handles stock allocation based on oldest purchase first (FIFO)
"""

from sqlalchemy.orm import Session
from app.models import Material, StockLedger, Issue, Supplier
from datetime import datetime
from typing import List, Dict

class FIFOService:
    """FIFO Stock Management"""
    
    @staticmethod
    def get_supplier_stock(db: Session, material_id: int) -> List[Dict]:
        """Get stock by supplier (oldest first)"""
        
        stock_entries = db.query(
            StockLedger.supplier_id,
            Supplier.name.label('supplier_name'),
            db.func.sum(StockLedger.quantity).label('total_qty'),
            db.func.min(StockLedger.created_at).label('first_date')
        ).outerjoin(Supplier, StockLedger.supplier_id == Supplier.id)\
         .filter(StockLedger.material_id == material_id)\
         .filter(StockLedger.transaction_type == 'receipt')\
         .group_by(StockLedger.supplier_id, Supplier.id, Supplier.name)\
         .order_by(db.func.min(StockLedger.created_at).asc())\
         .all()
        
        result = []
        for entry in stock_entries:
            # Calculate issued quantity
            issued = db.query(db.func.sum(StockLedger.quantity))\
                      .filter(StockLedger.material_id == material_id)\
                      .filter(StockLedger.supplier_id == entry.supplier_id)\
                      .filter(StockLedger.transaction_type == 'issue')\
                      .scalar() or 0
            
            available = entry.total_qty - issued
            
            if available > 0:
                result.append({
                    'supplier_id': entry.supplier_id,
                    'supplier_name': entry.supplier_name or f'Supplier {entry.supplier_id}',
                    'stock': available,
                    'purchase_date': entry.first_date.strftime('%Y-%m-%d') if entry.first_date else 'N/A'
                })
        
        return result
    
    @staticmethod
    def calculate_fifo_allocation(db: Session, material_id: int, quantity: int) -> Dict:
        """Calculate FIFO allocation"""
        
        supplier_stocks = FIFOService.get_supplier_stock(db, material_id)
        allocation = []
        total_allocated = 0
        
        for supplier_stock in supplier_stocks:
            if total_allocated >= quantity:
                allocation.append({
                    'supplier_id': supplier_stock['supplier_id'],
                    'supplier_name': supplier_stock['supplier_name'],
                    'available': supplier_stock['stock'],
                    'issue_qty': 0,
                    'remaining': supplier_stock['stock']
                })
            else:
                need = quantity - total_allocated
                issue_qty = min(need, supplier_stock['stock'])
                remaining = supplier_stock['stock'] - issue_qty
                
                allocation.append({
                    'supplier_id': supplier_stock['supplier_id'],
                    'supplier_name': supplier_stock['supplier_name'],
                    'available': supplier_stock['stock'],
                    'issue_qty': issue_qty,
                    'remaining': remaining
                })
                
                total_allocated += issue_qty
        
        total_available = sum(s['stock'] for s in supplier_stocks)
        
        return {
            'status': 'success' if total_allocated == quantity else 'insufficient',
            'total_available': total_available,
            'quantity_needed': quantity,
            'total_allocated': total_allocated,
            'allocation': allocation
        }
    
    @staticmethod
    def apply_fifo_issue(db: Session, material_id: int, quantity: int, user_id: int) -> Dict:
        """Apply FIFO and create issue"""
        
        allocation = FIFOService.calculate_fifo_allocation(db, material_id, quantity)
        
        if allocation['status'] == 'insufficient':
            return {
                'status': 'error',
                'message': f"Insufficient stock: {allocation['total_available']} available, {quantity} needed"
            }
        
        try:
            for item in allocation['allocation']:
                if item['issue_qty'] > 0:
                    ledger = StockLedger(
                        material_id=material_id,
                        supplier_id=item['supplier_id'],
                        transaction_type='issue',
                        quantity=-item['issue_qty'],
                        created_by=user_id,
                        remarks=f"FIFO Issue - {item['supplier_name']}"
                    )
                    db.add(ledger)
            
            db.commit()
            
            return {
                'status': 'success',
                'total_issued': allocation['total_allocated'],
                'allocation': allocation['allocation']
            }
        except Exception as e:
            db.rollback()
            return {'status': 'error', 'message': str(e)}
