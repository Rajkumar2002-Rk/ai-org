from sqlalchemy import Column, Integer, String, DECIMAL, TIMESTAMP
from backend.app.database import Base


class MenuItem(Base):
    __tablename__ = 'menu_items'

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    price = Column(DECIMAL, nullable=False)
    category = Column(String, nullable=False)
    description = Column(String, nullable=True)
    status = Column(String, nullable=False)
    source_name = Column(String, nullable=False)
    created_at = Column(TIMESTAMP, nullable=False)

