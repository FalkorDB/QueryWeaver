-- SQL Script: Table Creation (DDL) for MySQL CRM Database
-- This script creates the tables for your CRM database, adapted for MySQL syntax.

-- Drop existing tables to start fresh
SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS SalesOrderItems, SalesOrders, Invoices, Payments, Products, ProductCategories, Leads, Opportunities, Contacts, Customers, Campaigns, CampaignMembers, Tasks, Notes, Attachments, SupportTickets, TicketComments, Users, Roles, UserRoles;
SET FOREIGN_KEY_CHECKS = 1;

-- Roles for access control
CREATE TABLE Roles (
    RoleID INT AUTO_INCREMENT PRIMARY KEY COMMENT 'Unique identifier for the role.',
    RoleName VARCHAR(50) UNIQUE NOT NULL COMMENT 'Name of the role (e.g., "Admin", "Sales Representative").'
) COMMENT='Defines user roles for access control within the CRM (e.g., Admin, Sales Manager).';

-- Users of the CRM system
CREATE TABLE Users (
    UserID INT AUTO_INCREMENT PRIMARY KEY COMMENT 'Unique identifier for the user.',
    Username VARCHAR(50) NOT NULL UNIQUE COMMENT 'The username for logging in.',
    PasswordHash VARCHAR(255) NOT NULL COMMENT 'Hashed password for security.',
    Email VARCHAR(100) NOT NULL UNIQUE COMMENT 'The user\'s email address.',
    FirstName VARCHAR(50) COMMENT 'The user\'s first name.',
    LastName VARCHAR(50) COMMENT 'The user\'s last name.',
    CreatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'Timestamp when the user account was created.'
) COMMENT='Stores information about users who can log in to the CRM system.';

-- Junction table for Users and Roles
CREATE TABLE UserRoles (
    UserID INT NOT NULL COMMENT 'Foreign key referencing the Users table.',
    RoleID INT NOT NULL COMMENT 'Foreign key referencing the Roles table.',
    PRIMARY KEY (UserID, RoleID),
    FOREIGN KEY (UserID) REFERENCES Users(UserID) ON DELETE CASCADE,
    FOREIGN KEY (RoleID) REFERENCES Roles(RoleID) ON DELETE CASCADE
) COMMENT='Maps users to their assigned roles, supporting many-to-many relationships.';

-- Customer accounts
CREATE TABLE Customers (
    CustomerID INT AUTO_INCREMENT PRIMARY KEY COMMENT 'Unique identifier for the customer.',
    CustomerName VARCHAR(100) NOT NULL COMMENT 'The name of the customer company.',
    Industry VARCHAR(100) COMMENT 'The industry the customer belongs to.',
    Website VARCHAR(255) COMMENT 'The customer\'s official website.',
    Phone VARCHAR(30) COMMENT 'The customer\'s primary phone number.',
    Address VARCHAR(255) COMMENT 'The customer\'s physical address.',
    City VARCHAR(50) COMMENT 'The city part of the address.',
    State VARCHAR(50) COMMENT 'The state or province part of the address.',
    ZipCode VARCHAR(20) COMMENT 'The postal or zip code.',
    Country VARCHAR(50) COMMENT 'The country part of the address.',
    AssignedTo INT COMMENT 'The user (sales representative) assigned to this customer account.',
    CreatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'Timestamp when the customer was added.',
    FOREIGN KEY (AssignedTo) REFERENCES Users(UserID) ON DELETE SET NULL
) COMMENT='Represents customer accounts or companies.';

-- Individual contacts associated with customers
CREATE TABLE Contacts (
    ContactID INT AUTO_INCREMENT PRIMARY KEY COMMENT 'Unique identifier for the contact.',
    CustomerID INT NOT NULL COMMENT 'Foreign key linking the contact to a customer account.',
    FirstName VARCHAR(50) COMMENT 'The contact\'s first name.',
    LastName VARCHAR(50) COMMENT 'The contact\'s last name.',
    Email VARCHAR(100) COMMENT 'The contact\'s email address.',
    Phone VARCHAR(30) COMMENT 'The contact\'s phone number.',
    JobTitle VARCHAR(100) COMMENT 'The contact\'s job title or position.',
    CreatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'Timestamp when the contact was created.',
    FOREIGN KEY (CustomerID) REFERENCES Customers(CustomerID) ON DELETE CASCADE
) COMMENT='Stores information about individual contacts associated with customer accounts.';

-- Add more tables as needed, following the same pattern for MySQL compatibility.
