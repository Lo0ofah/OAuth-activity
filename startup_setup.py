import os
import sys
from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy import create_engine

Base = declarative_base()

class User(Base):
    __tablename__='user'

    id= Column(Integer, primary_key=True)
    name= Column(String(250),nullable=False)
    email= Column(String(250),nullable=False)
    picture= Column(String(250))

class Startup(Base):
    __tablename__ = 'startup'

    id = Column(Integer, primary_key=True)
    name = Column(String(250), nullable=False)
    user_id=Column(Integer,ForeignKey('user.id'))
    user= relationship(User)


class Founder(Base):
    __tablename__ = 'founder'

    name = Column(String(80), nullable=False)
    id = Column(Integer, primary_key=True)
    bio = Column(String(250))
    startup_id = Column(Integer, ForeignKey('startup.id'))
    startup = relationship(Startup)
    user_id=Column(Integer,ForeignKey('user.id'))
    user= relationship(User)


engine = create_engine('sqlite:///startup.db')


Base.metadata.create_all(engine)
