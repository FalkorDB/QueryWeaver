-- SQL Script 1 (Extended): Table Creation (DDL) with Comments
-- This script creates the tables for your CRM database and adds descriptions for each table and column.

-- Drop existing tables to start fresh
DROP TABLE IF EXISTS SalesOrderItems, SalesOrders, Invoices, Payments, Products, ProductCategories, Leads, Opportunities, Contacts, Customers, Campaigns, CampaignMembers, Tasks, Notes, Attachments, SupportTickets, TicketComments, Users, Roles, UserRoles CASCADE;

-- Roles for access control
CREATE TABLE Roles (
    RoleID SERIAL PRIMARY KEY,
    RoleName VARCHAR(50) UNIQUE NOT NULL
);
COMMENT ON TABLE Roles IS 'Defines user roles for access control within the CRM (e.g., Admin, Sales Manager).';
COMMENT ON COLUMN Roles.RoleID IS 'Unique identifier for the role.';
COMMENT ON COLUMN Roles.RoleName IS 'Name of the role (e.g., "Admin", "Sales Representative").';

-- Users of the CRM system
CREATE TABLE Users (
    UserID SERIAL PRIMARY KEY,
    Username VARCHAR(50) UNIQUE NOT NULL,
    PasswordHash VARCHAR(255) NOT NULL,
    Email VARCHAR(100) UNIQUE NOT NULL,
    FirstName VARCHAR(50),
    LastName VARCHAR(50),
    CreatedAt TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON TABLE Users IS 'Stores information about users who can log in to the CRM system.';
COMMENT ON COLUMN Users.UserID IS 'Unique identifier for the user.';
COMMENT ON COLUMN Users.Username IS 'The username for logging in.';
COMMENT ON COLUMN Users.PasswordHash IS 'Hashed password for security.';
COMMENT ON COLUMN Users.Email IS 'The user''s email address.';
COMMENT ON COLUMN Users.FirstName IS 'The user''s first name.';
COMMENT ON COLUMN Users.LastName IS 'The user''s last name.';
COMMENT ON COLUMN Users.CreatedAt IS 'Timestamp when the user account was created.';

-- Junction table for Users and Roles
CREATE TABLE UserRoles (
    UserID INT REFERENCES Users(UserID),
    RoleID INT REFERENCES Roles(RoleID),
    PRIMARY KEY (UserID, RoleID)
);
COMMENT ON TABLE UserRoles IS 'Maps users to their assigned roles, supporting many-to-many relationships.';
COMMENT ON COLUMN UserRoles.UserID IS 'Foreign key referencing the Users table.';
COMMENT ON COLUMN UserRoles.RoleID IS 'Foreign key referencing the Roles table.';

-- Customer accounts
CREATE TABLE Customers (
    CustomerID SERIAL PRIMARY KEY,
    CustomerName VARCHAR(100) NOT NULL,
    Industry VARCHAR(50),
    Website VARCHAR(100),
    Phone VARCHAR(20),
    Address VARCHAR(255),
    City VARCHAR(50),
    State VARCHAR(50),
    ZipCode VARCHAR(20),
    Country VARCHAR(50),
    AssignedTo INT REFERENCES Users(UserID),
    CreatedAt TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON TABLE Customers IS 'Represents customer accounts or companies.';
COMMENT ON COLUMN Customers.CustomerID IS 'Unique identifier for the customer.';
COMMENT ON COLUMN Customers.CustomerName IS 'The name of the customer company.';
COMMENT ON COLUMN Customers.Industry IS 'The industry the customer belongs to.';
COMMENT ON COLUMN Customers.Website IS 'The customer''s official website.';
COMMENT ON COLUMN Customers.Phone IS 'The customer''s primary phone number.';
COMMENT ON COLUMN Customers.Address IS 'The customer''s physical address.';
COMMENT ON COLUMN Customers.City IS 'The city part of the address.';
COMMENT ON COLUMN Customers.State IS 'The state or province part of the address.';
COMMENT ON COLUMN Customers.ZipCode IS 'The postal or zip code.';
COMMENT ON COLUMN Customers.Country IS 'The country part of the address.';
COMMENT ON COLUMN Customers.AssignedTo IS 'The user (sales representative) assigned to this customer account.';
COMMENT ON COLUMN Customers.CreatedAt IS 'Timestamp when the customer was added.';

-- Individual contacts associated with customers
CREATE TABLE Contacts (
    ContactID SERIAL PRIMARY KEY,
    CustomerID INT REFERENCES Customers(CustomerID),
    FirstName VARCHAR(50) NOT NULL,
    LastName VARCHAR(50) NOT NULL,
    Email VARCHAR(100) UNIQUE,
    Phone VARCHAR(20),
    JobTitle VARCHAR(50),
    CreatedAt TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON TABLE Contacts IS 'Stores information about individual contacts associated with customer accounts.';
COMMENT ON COLUMN Contacts.ContactID IS 'Unique identifier for the contact.';
COMMENT ON COLUMN Contacts.CustomerID IS 'Foreign key linking the contact to a customer account.';
COMMENT ON COLUMN Contacts.FirstName IS 'The contact''s first name.';
COMMENT ON COLUMN Contacts.LastName IS 'The contact''s last name.';
COMMENT ON COLUMN Contacts.Email IS 'The contact''s email address.';
COMMENT ON COLUMN Contacts.Phone IS 'The contact''s phone number.';
COMMENT ON COLUMN Contacts.JobTitle IS 'The contact''s job title or position.';
COMMENT ON COLUMN Contacts.CreatedAt IS 'Timestamp when the contact was created.';

-- Potential sales leads
CREATE TABLE Leads (
    LeadID SERIAL PRIMARY KEY,
    FirstName VARCHAR(50),
    LastName VARCHAR(50),
    Email VARCHAR(100),
    Phone VARCHAR(20),
    Company VARCHAR(100),
    Status VARCHAR(50) DEFAULT 'New',
    Source VARCHAR(50),
    AssignedTo INT REFERENCES Users(UserID),
    CreatedAt TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON TABLE Leads IS 'Represents potential customers or sales prospects (not yet qualified).';
COMMENT ON COLUMN Leads.LeadID IS 'Unique identifier for the lead.';
COMMENT ON COLUMN Leads.Status IS 'Current status of the lead (e.g., New, Contacted, Qualified, Lost).';
COMMENT ON COLUMN Leads.Source IS 'The source from which the lead was generated (e.g., Website, Referral).';
COMMENT ON COLUMN Leads.AssignedTo IS 'The user assigned to follow up with this lead.';
COMMENT ON COLUMN Leads.CreatedAt IS 'Timestamp when the lead was created.';

-- Sales opportunities
CREATE TABLE Opportunities (
    OpportunityID SERIAL PRIMARY KEY,
    CustomerID INT REFERENCES Customers(CustomerID),
    OpportunityName VARCHAR(100) NOT NULL,
    Stage VARCHAR(50) DEFAULT 'Prospecting',
    Amount DECIMAL(12, 2),
    CloseDate DATE,
    AssignedTo INT REFERENCES Users(UserID),
    CreatedAt TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON TABLE Opportunities IS 'Tracks qualified sales deals with potential revenue.';
COMMENT ON COLUMN Opportunities.OpportunityID IS 'Unique identifier for the opportunity.';
COMMENT ON COLUMN Opportunities.CustomerID IS 'Foreign key linking the opportunity to a customer account.';
COMMENT ON COLUMN Opportunities.OpportunityName IS 'A descriptive name for the sales opportunity.';
COMMENT ON COLUMN Opportunities.Stage IS 'The current stage in the sales pipeline (e.g., Prospecting, Proposal, Closed Won).';
COMMENT ON COLUMN Opportunities.Amount IS 'The estimated value of the opportunity.';
COMMENT ON COLUMN Opportunities.CloseDate IS 'The expected date the deal will close.';
COMMENT ON COLUMN Opportunities.AssignedTo IS 'The user responsible for this opportunity.';
COMMENT ON COLUMN Opportunities.CreatedAt IS 'Timestamp when the opportunity was created.';

-- Product categories
CREATE TABLE ProductCategories (
    CategoryID SERIAL PRIMARY KEY,
    CategoryName VARCHAR(50) NOT NULL,
    Description TEXT
);
COMMENT ON TABLE ProductCategories IS 'Used to group products into categories (e.g., Software, Hardware).';
COMMENT ON COLUMN ProductCategories.CategoryID IS 'Unique identifier for the category.';
COMMENT ON COLUMN ProductCategories.CategoryName IS 'Name of the product category.';
COMMENT ON COLUMN ProductCategories.Description IS 'A brief description of the category.';

-- Products or services offered
CREATE TABLE Products (
    ProductID SERIAL PRIMARY KEY,
    ProductName VARCHAR(100) NOT NULL,
    CategoryID INT REFERENCES ProductCategories(CategoryID),
    Description TEXT,
    Price DECIMAL(10, 2) NOT NULL,
    StockQuantity INT DEFAULT 0
);
COMMENT ON TABLE Products IS 'Stores details of the products or services the company sells.';
COMMENT ON COLUMN Products.ProductID IS 'Unique identifier for the product.';
COMMENT ON COLUMN Products.ProductName IS 'Name of the product.';
COMMENT ON COLUMN Products.CategoryID IS 'Foreign key linking the product to a category.';
COMMENT ON COLUMN Products.Description IS 'Detailed description of the product.';
COMMENT ON COLUMN Products.Price IS 'The unit price of the product.';
COMMENT ON COLUMN Products.StockQuantity IS 'The quantity of the product available in stock.';

-- Sales orders
CREATE TABLE SalesOrders (
    OrderID SERIAL PRIMARY KEY,
    CustomerID INT REFERENCES Customers(CustomerID),
    OpportunityID INT REFERENCES Opportunities(OpportunityID),
    OrderDate DATE NOT NULL,
    Status VARCHAR(50) DEFAULT 'Pending',
    TotalAmount DECIMAL(12, 2),
    AssignedTo INT REFERENCES Users(UserID)
);
COMMENT ON TABLE SalesOrders IS 'Records of confirmed sales to customers.';
COMMENT ON COLUMN SalesOrders.OrderID IS 'Unique identifier for the sales order.';
COMMENT ON COLUMN SalesOrders.CustomerID IS 'Foreign key linking the order to a customer.';
COMMENT ON COLUMN SalesOrders.OpportunityID IS 'Foreign key linking the order to the sales opportunity it came from.';
COMMENT ON COLUMN SalesOrders.OrderDate IS 'The date the order was placed.';
COMMENT ON COLUMN SalesOrders.Status IS 'The current status of the order (e.g., Pending, Shipped, Canceled).';
COMMENT ON COLUMN SalesOrders.TotalAmount IS 'The total calculated amount for the order.';
COMMENT ON COLUMN SalesOrders.AssignedTo IS 'The user who processed the order.';

-- Items within a sales order
CREATE TABLE SalesOrderItems (
    OrderItemID SERIAL PRIMARY KEY,
    OrderID INT REFERENCES SalesOrders(OrderID) ON DELETE CASCADE,
    ProductID INT REFERENCES Products(ProductID),
    Quantity INT NOT NULL,
    UnitPrice DECIMAL(10, 2) NOT NULL
);
COMMENT ON TABLE SalesOrderItems IS 'Line items for each product within a sales order.';
COMMENT ON COLUMN SalesOrderItems.OrderItemID IS 'Unique identifier for the order item.';
COMMENT ON COLUMN SalesOrderItems.OrderID IS 'Foreign key linking this item to a sales order.';
COMMENT ON COLUMN SalesOrderItems.ProductID IS 'Foreign key linking to the product being ordered.';
COMMENT ON COLUMN SalesOrderItems.Quantity IS 'The quantity of the product ordered.';
COMMENT ON COLUMN SalesOrderItems.UnitPrice IS 'The price per unit at the time of sale.';

-- Invoices for sales
CREATE TABLE Invoices (
    InvoiceID SERIAL PRIMARY KEY,
    OrderID INT REFERENCES SalesOrders(OrderID),
    InvoiceDate DATE NOT NULL,
    DueDate DATE,
    TotalAmount DECIMAL(12, 2),
    Status VARCHAR(50) DEFAULT 'Unpaid'
);
COMMENT ON TABLE Invoices IS 'Represents billing invoices sent to customers.';
COMMENT ON COLUMN Invoices.InvoiceID IS 'Unique identifier for the invoice.';
COMMENT ON COLUMN Invoices.OrderID IS 'Foreign key linking the invoice to a sales order.';
COMMENT ON COLUMN Invoices.InvoiceDate IS 'The date the invoice was issued.';
COMMENT ON COLUMN Invoices.DueDate IS 'The date the payment is due.';
COMMENT ON COLUMN Invoices.TotalAmount IS 'The total amount due on the invoice.';
COMMENT ON COLUMN Invoices.Status IS 'The payment status of the invoice (e.g., Unpaid, Paid, Overdue).';

-- Payment records
CREATE TABLE Payments (
    PaymentID SERIAL PRIMARY KEY,
    InvoiceID INT REFERENCES Invoices(InvoiceID),
    PaymentDate DATE NOT NULL,
    Amount DECIMAL(12, 2),
    PaymentMethod VARCHAR(50)
);
COMMENT ON TABLE Payments IS 'Tracks payments received from customers against invoices.';
COMMENT ON COLUMN Payments.PaymentID IS 'Unique identifier for the payment.';
COMMENT ON COLUMN Payments.InvoiceID IS 'Foreign key linking the payment to an invoice.';
COMMENT ON COLUMN Payments.PaymentDate IS 'The date the payment was received.';
COMMENT ON COLUMN Payments.Amount IS 'The amount that was paid.';
COMMENT ON COLUMN Payments.PaymentMethod IS 'The method of payment (e.g., Credit Card, Bank Transfer).';

-- Marketing campaigns
CREATE TABLE Campaigns (
    CampaignID SERIAL PRIMARY KEY,
    CampaignName VARCHAR(100) NOT NULL,
    StartDate DATE,
    EndDate DATE,
    Budget DECIMAL(12, 2),
    Status VARCHAR(50),
    Owner INT REFERENCES Users(UserID)
);
COMMENT ON TABLE Campaigns IS 'Stores information about marketing campaigns.';
COMMENT ON COLUMN Campaigns.CampaignID IS 'Unique identifier for the campaign.';
COMMENT ON COLUMN Campaigns.CampaignName IS 'The name of the marketing campaign.';
COMMENT ON COLUMN Campaigns.StartDate IS 'The start date of the campaign.';
COMMENT ON COLUMN Campaigns.EndDate IS 'The end date of the campaign.';
COMMENT ON COLUMN Campaigns.Budget IS 'The allocated budget for the campaign.';
COMMENT ON COLUMN Campaigns.Status IS 'The current status of the campaign (e.g., Planned, Active, Completed).';
COMMENT ON COLUMN Campaigns.Owner IS 'The user responsible for the campaign.';

-- Members of a marketing campaign (leads or contacts)
CREATE TABLE CampaignMembers (
    CampaignMemberID SERIAL PRIMARY KEY,
    CampaignID INT REFERENCES Campaigns(CampaignID),
    LeadID INT REFERENCES Leads(LeadID),
    ContactID INT REFERENCES Contacts(ContactID),
    Status VARCHAR(50)
);
COMMENT ON TABLE CampaignMembers IS 'Links leads and contacts to the marketing campaigns they are a part of.';
COMMENT ON COLUMN CampaignMembers.CampaignMemberID IS 'Unique identifier for the campaign member record.';
COMMENT ON COLUMN CampaignMembers.CampaignID IS 'Foreign key linking to the campaign.';
COMMENT ON COLUMN CampaignMembers.LeadID IS 'Foreign key linking to a lead (if the member is a lead).';
COMMENT ON COLUMN CampaignMembers.ContactID IS 'Foreign key linking to a contact (if the member is a contact).';
COMMENT ON COLUMN CampaignMembers.Status IS 'The status of the member in the campaign (e.g., Sent, Responded).';

-- Tasks for users
CREATE TABLE Tasks (
    TaskID SERIAL PRIMARY KEY,
    Title VARCHAR(100) NOT NULL,
    Description TEXT,
    DueDate DATE,
    Status VARCHAR(50) DEFAULT 'Not Started',
    Priority VARCHAR(20) DEFAULT 'Normal',
    AssignedTo INT REFERENCES Users(UserID),
    RelatedToEntity VARCHAR(50),
    RelatedToID INT
);
COMMENT ON TABLE Tasks IS 'Tracks tasks or to-do items for CRM users.';
COMMENT ON COLUMN Tasks.TaskID IS 'Unique identifier for the task.';
COMMENT ON COLUMN Tasks.Title IS 'A short title for the task.';
COMMENT ON COLUMN Tasks.Description IS 'A detailed description of the task.';
COMMENT ON COLUMN Tasks.DueDate IS 'The date the task is due to be completed.';
COMMENT ON COLUMN Tasks.Status IS 'The current status of the task (e.g., Not Started, In Progress, Completed).';
COMMENT ON COLUMN Tasks.Priority IS 'The priority level of the task (e.g., Low, Normal, High).';
COMMENT ON COLUMN Tasks.AssignedTo IS 'The user the task is assigned to.';
COMMENT ON COLUMN Tasks.RelatedToEntity IS 'The type of record this task is related to (e.g., ''Lead'', ''Opportunity'').';
COMMENT ON COLUMN Tasks.RelatedToID IS 'The ID of the related record.';

-- Notes related to various records
CREATE TABLE Notes (
    NoteID SERIAL PRIMARY KEY,
    Content TEXT NOT NULL,
    CreatedBy INT REFERENCES Users(UserID),
    RelatedToEntity VARCHAR(50),
    RelatedToID INT,
    CreatedAt TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON TABLE Notes IS 'Allows users to add notes to various records (e.g., contacts, opportunities).';
COMMENT ON COLUMN Notes.NoteID IS 'Unique identifier for the note.';
COMMENT on COLUMN Notes.Content IS 'The text content of the note.';
COMMENT ON COLUMN Notes.CreatedBy IS 'The user who created the note.';
COMMENT ON COLUMN Notes.RelatedToEntity IS 'The type of record this note is related to (e.g., ''Contact'', ''Customer'').';
COMMENT ON COLUMN Notes.RelatedToID IS 'The ID of the related record.';
COMMENT ON COLUMN Notes.CreatedAt IS 'Timestamp when the note was created.';

-- File attachments
CREATE TABLE Attachments (
    AttachmentID SERIAL PRIMARY KEY,
    FileName VARCHAR(255) NOT NULL,
    FilePath VARCHAR(255) NOT NULL,
    FileSize INT,
    FileType VARCHAR(100),
    UploadedBy INT REFERENCES Users(UserID),
    RelatedToEntity VARCHAR(50),
    RelatedToID INT,
    CreatedAt TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON TABLE Attachments IS 'Stores metadata about files attached to records in the CRM.';
COMMENT ON COLUMN Attachments.AttachmentID IS 'Unique identifier for the attachment.';
COMMENT ON COLUMN Attachments.FileName IS 'The original name of the uploaded file.';
COMMENT ON COLUMN Attachments.FilePath IS 'The path where the file is stored on the server.';
COMMENT ON COLUMN Attachments.FileSize IS 'The size of the file in bytes.';
COMMENT ON COLUMN Attachments.FileType IS 'The MIME type of the file (e.g., ''application/pdf'').';
COMMENT ON COLUMN Attachments.UploadedBy IS 'The user who uploaded the file.';
COMMENT ON COLUMN Attachments.RelatedToEntity IS 'The type of record this attachment is related to.';
COMMENT ON COLUMN Attachments.RelatedToID IS 'The ID of the related record.';
COMMENT ON COLUMN Attachments.CreatedAt IS 'Timestamp when the file was uploaded.';

-- Customer support tickets
CREATE TABLE SupportTickets (
    TicketID SERIAL PRIMARY KEY,
    CustomerID INT REFERENCES Customers(CustomerID),
    ContactID INT REFERENCES Contacts(ContactID),
    Subject VARCHAR(255) NOT NULL,
    Description TEXT,
    Status VARCHAR(50) DEFAULT 'Open',
    Priority VARCHAR(20) DEFAULT 'Normal',
    AssignedTo INT REFERENCES Users(UserID),
    CreatedAt TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON TABLE SupportTickets IS 'Tracks customer service and support requests.';
COMMENT ON COLUMN SupportTickets.TicketID IS 'Unique identifier for the support ticket.';
COMMENT ON COLUMN SupportTickets.CustomerID IS 'Foreign key linking the ticket to a customer.';
COMMENT ON COLUMN SupportTickets.ContactID IS 'Foreign key linking the ticket to a specific contact.';
COMMENT ON COLUMN SupportTickets.Subject IS 'A brief summary of the support issue.';
COMMENT ON COLUMN SupportTickets.Description IS 'A detailed description of the issue.';
COMMENT ON COLUMN SupportTickets.Status IS 'The current status of the ticket (e.g., Open, In Progress, Resolved).';
COMMENT ON COLUMN SupportTickets.Priority IS 'The priority of the ticket (e.g., Low, Normal, High).';
COMMENT ON COLUMN SupportTickets.AssignedTo IS 'The support agent the ticket is assigned to.';
COMMENT ON COLUMN SupportTickets.CreatedAt IS 'Timestamp when the ticket was created.';

-- Comments on support tickets
CREATE TABLE TicketComments (
    CommentID SERIAL PRIMARY KEY,
    TicketID INT REFERENCES SupportTickets(TicketID) ON DELETE CASCADE,
    Comment TEXT NOT NULL,
    CreatedBy INT REFERENCES Users(UserID),
    CreatedAt TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON TABLE TicketComments IS 'Stores comments and updates related to a support ticket.';
COMMENT ON COLUMN TicketComments.CommentID IS 'Unique identifier for the comment.';
COMMENT ON COLUMN TicketComments.TicketID IS 'Foreign key linking the comment to a support ticket.';
COMMENT ON COLUMN TicketComments.Comment IS 'The text content of the comment.';
COMMENT ON COLUMN TicketComments.CreatedBy IS 'The user who added the comment.';
COMMENT ON COLUMN TicketComments.CreatedAt IS 'Timestamp when the comment was added.';


-- SQL Script 2: Data Insertion (DML)
-- This script populates the tables with sample data.

-- Insert Roles
INSERT INTO Roles (RoleName) VALUES ('Admin'), ('Sales Manager'), ('Sales Representative'), ('Support Agent');

-- Insert Users
INSERT INTO Users (Username, PasswordHash, Email, FirstName, LastName) VALUES
('admin', 'hashed_password', 'admin@example.com', 'Admin', 'User'),
('sales_manager', 'hashed_password', 'manager@example.com', 'John', 'Doe'),
('sales_rep1', 'hashed_password', 'rep1@example.com', 'Jane', 'Smith'),
('sales_rep2', 'hashed_password', 'rep2@example.com', 'Peter', 'Jones'),
('support_agent1', 'hashed_password', 'support1@example.com', 'Mary', 'Williams');

-- Assign Roles to Users
INSERT INTO UserRoles (UserID, RoleID) VALUES
(1, 1), (2, 2), (3, 3), (4, 3), (5, 4);

-- Insert Customers
INSERT INTO Customers (CustomerName, Industry, Website, Phone, Address, City, State, ZipCode, Country, AssignedTo) VALUES
('ABC Corporation', 'Technology', 'http://www.abccorp.com', '123-456-7890', '123 Tech Park', 'Techville', 'CA', '90210', 'USA', 3),
('Innovate Inc.', 'Software', 'http://www.innovate.com', '234-567-8901', '456 Innovation Dr', 'Devtown', 'TX', '75001', 'USA', 4),
('Global Solutions', 'Consulting', 'http://www.globalsolutions.com', '345-678-9012', '789 Global Ave', 'Businesston', 'NY', '10001', 'USA', 3),
('Data Dynamics', 'Analytics', 'http://www.datadynamics.com', '456-123-7890', '789 Data Dr', 'Metropolis', 'IL', '60601', 'USA', 4),
('Synergy Solutions', 'HR', 'http://www.synergysolutions.com', '789-456-1230', '101 Synergy Blvd', 'Union City', 'NJ', '07087', 'USA', 3);

-- Insert Contacts
INSERT INTO Contacts (CustomerID, FirstName, LastName, Email, Phone, JobTitle) VALUES
(1, 'Alice', 'Wonder', 'alice.wonder@abccorp.com', '123-456-7891', 'CTO'),
(1, 'Bob', 'Builder', 'bob.builder@abccorp.com', '123-456-7892', 'Project Manager'),
(2, 'Charlie', 'Chocolate', 'charlie.chocolate@innovate.com', '234-567-8902', 'CEO'),
(3, 'Diana', 'Prince', 'diana.prince@globalsolutions.com', '345-678-9013', 'Consultant'),
(4, 'Leo', 'Lytics', 'leo.lytics@datadynamics.com', '456-123-7891', 'Data Scientist'),
(5, 'Hannah', 'Resources', 'hannah.r@synergysolutions.com', '789-456-1231', 'HR Manager');

-- Insert Leads
INSERT INTO Leads (FirstName, LastName, Email, Phone, Company, Status, Source, AssignedTo) VALUES
('Eve', 'Apple', 'eve.apple@email.com', '456-789-0123', 'Future Gadgets', 'Qualified', 'Website', 3),
('Frank', 'Stein', 'frank.stein@email.com', '567-890-1234', 'Monster Corp', 'New', 'Referral', 4),
('Grace', 'Hopper', 'grace.hopper@email.com', '678-901-2345', 'Cobol Inc.', 'Contacted', 'Cold Call', 3),
('Ivy', 'Green', 'ivy.g@webmail.com', '890-123-4567', 'Eco Systems', 'New', 'Trade Show', 4),
('Jack', 'Nimble', 'jack.n@fastmail.com', '901-234-5678', 'Quick Corp', 'Qualified', 'Website', 3);

-- Insert Opportunities
INSERT INTO Opportunities (CustomerID, OpportunityName, Stage, Amount, CloseDate, AssignedTo) VALUES
(1, 'ABC Corp Website Redesign', 'Proposal', 50000.00, '2025-08-30', 3),
(2, 'Innovate Inc. Mobile App', 'Qualification', 75000.00, '2025-09-15', 4),
(3, 'Global Solutions IT Consulting', 'Negotiation', 120000.00, '2025-08-20', 3),
(4, 'Analytics Platform Subscription', 'Proposal', 90000.00, '2025-09-30', 4),
(5, 'HR Software Implementation', 'Prospecting', 65000.00, '2025-10-25', 3);

-- Insert Product Categories
INSERT INTO ProductCategories (CategoryName, Description) VALUES
('Software', 'Business and productivity software'),
('Hardware', 'Computer hardware and peripherals'),
('Services', 'Consulting and support services');

-- Insert Products
INSERT INTO Products (ProductName, CategoryID, Description, Price, StockQuantity) VALUES
('CRM Pro', 1, 'Advanced CRM Software Suite', 1500.00, 100),
('Office Laptop Model X', 2, 'High-performance laptop for business', 1200.00, 50),
('IT Support Package', 3, '24/7 IT support services', 300.00, 200),
('Analytics Dashboard Pro', 1, 'Advanced analytics dashboard', 2500.00, 75),
('Ergonomic Office Chair', 2, 'Comfortable chair for long hours', 350.00, 150);

-- Insert Sales Orders
INSERT INTO SalesOrders (CustomerID, OpportunityID, OrderDate, Status, TotalAmount, AssignedTo) VALUES
(1, 1, '2025-07-20', 'Shipped', 1500.00, 3),
(2, 2, '2025-07-22', 'Pending', 2400.00, 4),
(3, 3, '2025-07-24', 'Delivered', 300.00, 3),
(4, 4, '2025-07-25', 'Pending', 2500.00, 4);

-- Insert Sales Order Items
INSERT INTO SalesOrderItems (OrderID, ProductID, Quantity, UnitPrice) VALUES
(1, 1, 1, 1500.00),
(2, 2, 2, 1200.00),
(3, 3, 1, 300.00),
(4, 4, 1, 2500.00);

-- Insert Invoices
INSERT INTO Invoices (OrderID, InvoiceDate, DueDate, TotalAmount, Status) VALUES
(1, '2025-07-21', '2025-08-20', 1500.00, 'Paid'),
(2, '2025-07-23', '2025-08-22', 2400.00, 'Unpaid'),
(3, '2025-07-24', '2025-08-23', 300.00, 'Paid'),
(4, '2025-07-25', '2025-08-24', 2500.00, 'Unpaid');

-- Insert Payments
INSERT INTO Payments (InvoiceID, PaymentDate, Amount, PaymentMethod) VALUES
(1, '2025-07-25', 1500.00, 'Credit Card'),
(3, '2025-07-25', 300.00, 'Bank Transfer');

-- Insert Campaigns
INSERT INTO Campaigns (CampaignName, StartDate, EndDate, Budget, Status, Owner) VALUES
('Summer Sale 2025', '2025-06-01', '2025-08-31', 10000.00, 'Active', 2),
('Q4 Product Launch', '2025-10-01', '2025-12-31', 25000.00, 'Planned', 2);

-- Insert Campaign Members
INSERT INTO CampaignMembers (CampaignID, LeadID, Status) VALUES
(1, 1, 'Responded'),
(1, 2, 'Sent'),
(1, 4, 'Sent');
INSERT INTO CampaignMembers (CampaignID, ContactID, Status) VALUES
(1, 4, 'Sent'),
(1, 5, 'Responded');

-- Insert Tasks
INSERT INTO Tasks (Title, Description, DueDate, Status, Priority, AssignedTo, RelatedToEntity, RelatedToID) VALUES
('Follow up with ABC Corp', 'Discuss proposal details', '2025-08-01', 'In Progress', 'High', 3, 'Opportunity', 1),
('Prepare demo for Innovate Inc.', 'Customize demo for their needs', '2025-08-05', 'Not Started', 'Normal', 4, 'Opportunity', 2),
('Send updated proposal to Global Solutions', 'Include new service terms', '2025-07-28', 'Completed', 'High', 3, 'Opportunity', 3),
('Schedule initial call with Synergy Solutions', 'Discuss HR software needs', '2025-08-02', 'Not Started', 'Normal', 3, 'Customer', 5);

-- Insert Notes
INSERT INTO Notes (Content, CreatedBy, RelatedToEntity, RelatedToID) VALUES
('Alice is very interested in the mobile integration features.', 3, 'Contact', 1),
('Lead from the tech conference last week.', 4, 'Lead', 2),
('Customer is looking for a cloud-based solution.', 4, 'Opportunity', 4),
('Met Ivy at the GreenTech expo. Promising lead.', 4, 'Lead', 4);

-- Insert Attachments
INSERT INTO Attachments (FileName, FilePath, FileSize, FileType, UploadedBy, RelatedToEntity, RelatedToID) VALUES
('proposal_v1.pdf', '/attachments/proposal_v1.pdf', 102400, 'application/pdf', 3, 'Opportunity', 1),
('analytics_brochure.pdf', '/attachments/analytics_brochure.pdf', 256000, 'application/pdf', 4, 'Opportunity', 4);

-- Insert Support Tickets
INSERT INTO SupportTickets (CustomerID, ContactID, Subject, Description, Status, Priority, AssignedTo) VALUES
(1, 1, 'Cannot login to portal', 'User Alice Wonder is unable to access the customer portal.', 'Resolved', 'High', 5),
(2, 3, 'Billing question', 'Question about the last invoice.', 'In Progress', 'Normal', 5),
(3, 4, 'Feature Request: Dark Mode', 'Requesting dark mode for the user dashboard.', 'Open', 'Low', 5),
(1, 2, 'Integration issue with calendar', 'Tasks are not syncing with Google Calendar.', 'In Progress', 'High', 5);

-- Insert Ticket Comments
INSERT INTO TicketComments (TicketID, Comment, CreatedBy) VALUES
(1, 'Have reset the password. Please ask the user to try again.', 5),
(1, 'User confirmed they can now log in. Closing the ticket.', 5),
(2, 'Checking API logs for sync errors.', 5),
(3, 'Feature has been added to the development backlog.', 5);

-- SQL Script 3: Insert More Demo Data (DML)
-- This script adds more sample data to the CRM database.
-- Run this script AFTER running 1_create_tables.sql and 2_insert_data.sql.

-- Insert more Customers (starting from CustomerID 6)
INSERT INTO Customers (CustomerName, Industry, Website, Phone, Address, City, State, ZipCode, Country, AssignedTo) VALUES
('Quantum Innovations', 'R&D', 'http://www.quantuminnovate.com', '555-0101', '100 Research Pkwy', 'Quantumville', 'MA', '02139', 'USA', 3),
('HealthFirst Medical', 'Healthcare', 'http://www.healthfirst.com', '555-0102', '200 Health Blvd', 'Wellnesston', 'FL', '33101', 'USA', 4),
('GreenScape Solutions', 'Environmental', 'http://www.greenscape.com', '555-0103', '300 Nature Way', 'Ecoville', 'OR', '97201', 'USA', 3),
('Pinnacle Finance', 'Finance', 'http://www.pinnaclefinance.com', '555-0104', '400 Wall St', 'Financeton', 'NY', '10005', 'USA', 4),
('Creative Minds Agency', 'Marketing', 'http://www.creativeminds.com', '555-0105', '500 Ad Ave', 'Creator City', 'CA', '90028', 'USA', 3);

-- Insert more Contacts (starting from ContactID 7)
-- Assuming CustomerIDs 6-10 were just created
INSERT INTO Contacts (CustomerID, FirstName, LastName, Email, Phone, JobTitle) VALUES
(6, 'Quentin', 'Physics', 'q.physics@quantuminnovate.com', '555-0101-1', 'Lead Scientist'),
(7, 'Helen', 'Healer', 'h.healer@healthfirst.com', '555-0102-1', 'Hospital Administrator'),
(7, 'Marcus', 'Welby', 'm.welby@healthfirst.com', '555-0102-2', 'Chief of Medicine'),
(8, 'Gary', 'Gardener', 'g.gardener@greenscape.com', '555-0103-1', 'CEO'),
(9, 'Fiona', 'Funds', 'f.funds@pinnaclefinance.com', '555-0104-1', 'Investment Banker'),
(10, 'Chris', 'Creative', 'c.creative@creativeminds.com', '555-0105-1', 'Art Director'),
(1, 'Carol', 'Client', 'c.client@abccorp.com', '123-456-7893', 'IT Director'); -- Contact for existing customer

-- Insert more Leads (starting from LeadID 6)
INSERT INTO Leads (FirstName, LastName, Email, Phone, Company, Status, Source, AssignedTo) VALUES
('Ken', 'Knowledge', 'ken.k@university.edu', '555-0201', 'State University', 'Contacted', 'Referral', 4),
('Laura', 'Legal', 'laura.l@lawfirm.com', '555-0202', 'Law & Order LLC', 'New', 'Website', 3),
('Mike', 'Mechanic', 'mike.m@autoshop.com', '555-0203', 'Auto Fixers', 'Lost', 'Cold Call', 4),
('Nancy', 'Nurse', 'nancy.n@clinic.com', '555-0204', 'Community Clinic', 'Qualified', 'Trade Show', 3),
('Oscar', 'Organizer', 'oscar.o@events.com', '555-0205', 'Events R Us', 'New', 'Website', 4);

-- Insert more Opportunities (starting from OpportunityID 6)
-- Assuming CustomerIDs 6-10 were just created
INSERT INTO Opportunities (CustomerID, OpportunityName, Stage, Amount, CloseDate, AssignedTo) VALUES
(6, 'Quantum Computing Simulation Software', 'Qualification', 250000.00, '2025-11-15', 3),
(7, 'Patient Management System Upgrade', 'Proposal', 180000.00, '2025-12-01', 4),
(8, 'Environmental Impact Reporting Tool', 'Negotiation', 75000.00, '2025-10-30', 3),
(9, 'Wealth Management Platform', 'Closed Won', 300000.00, '2025-07-25', 4),
(10, 'Digital Marketing Campaign Analytics', 'Prospecting', 45000.00, '2025-11-20', 3);

-- Insert a new Product Category first
INSERT INTO ProductCategories (CategoryName, Description) VALUES
('Cloud Solutions', 'Cloud-based infrastructure and platforms'); -- This will be CategoryID 4

-- Insert more Products (starting from ProductID 6)
INSERT INTO Products (ProductName, CategoryID, Description, Price, StockQuantity) VALUES
('Wealth Management Suite', 1, 'Comprehensive software for financial advisors', 5000.00, 50),
('Patient Record System', 1, 'EHR system for clinics and hospitals', 4500.00, 80),
('Cloud Storage - 10TB Plan', 4, '10TB of enterprise cloud storage', 1000.00, 500);

-- Insert more Sales Orders (starting from OrderID 5)
-- For the 'Closed Won' opportunity (ID 9)
INSERT INTO SalesOrders (CustomerID, OpportunityID, OrderDate, Status, TotalAmount, AssignedTo) VALUES
(9, 9, '2025-07-26', 'Delivered', 5000.00, 4);

-- Insert more Sales Order Items (for OrderID 5)
INSERT INTO SalesOrderItems (OrderID, ProductID, Quantity, UnitPrice) VALUES
(5, 6, 1, 5000.00); -- Wealth Management Suite (ProductID 6)

-- Insert more Invoices (starting from InvoiceID 5)
INSERT INTO Invoices (OrderID, InvoiceDate, DueDate, TotalAmount, Status) VALUES
(5, '2025-07-26', '2025-08-25', 5000.00, 'Paid');

-- Insert more Payments (starting from PaymentID 3)
INSERT INTO Payments (InvoiceID, PaymentDate, Amount, PaymentMethod) VALUES
(2, '2025-07-25', 2400.00, 'Bank Transfer'), -- Payment for an existing unpaid invoice
(5, '2025-07-26', 5000.00, 'Credit Card');

-- Insert a new Campaign (starting from CampaignID 3)
INSERT INTO Campaigns (CampaignName, StartDate, EndDate, Budget, Status, Owner) VALUES
('Healthcare Solutions Webinar', '2025-09-01', '2025-09-30', 7500.00, 'Planned', 2);

-- Insert more Campaign Members
INSERT INTO CampaignMembers (CampaignID, LeadID, Status) VALUES
(3, 9, 'Sent'); -- Nancy Nurse (LeadID 9) for Healthcare campaign
INSERT INTO CampaignMembers (CampaignID, ContactID, Status) VALUES
(3, 8, 'Sent'), -- Helen Healer (ContactID 8)
(3, 9, 'Responded'); -- Marcus Welby (ContactID 9)

-- Insert more Tasks (starting from TaskID 5)
INSERT INTO Tasks (Title, Description, DueDate, Status, Priority, AssignedTo, RelatedToEntity, RelatedToID) VALUES
('Draft contract for Pinnacle Finance', 'Based on the final negotiation terms.', '2025-07-28', 'Completed', 'High', 4, 'Opportunity', 9),
('Schedule webinar with HealthFirst', 'Discuss Patient Management System demo.', '2025-08-10', 'Not Started', 'High', 4, 'Opportunity', 7),
('Research Quantum Innovations needs', 'Prepare for qualification call.', '2025-08-15', 'In Progress', 'Normal', 3, 'Opportunity', 6),
('Call Nancy Nurse to follow up', 'Follow up from trade show conversation.', '2025-08-05', 'Not Started', 'Normal', 3, 'Lead', 9);

-- Insert more Notes (starting from NoteID 5)
INSERT INTO Notes (Content, CreatedBy, RelatedToEntity, RelatedToID) VALUES
('Pinnacle deal closed! Great work team.', 2, 'Opportunity', 9),
('GreenScape is looking for a solution before year-end for compliance reasons.', 3, 'Opportunity', 8),
('Nancy was very engaged at the booth, good prospect.', 3, 'Lead', 9);

-- Insert more Support Tickets (starting from TicketID 5)
INSERT INTO SupportTickets (CustomerID, ContactID, Subject, Description, Status, Priority, AssignedTo) VALUES
(4, 5, 'Dashboard data not refreshing', 'The main dashboard widgets are not updating in real-time.', 'Open', 'High', 5),
(5, 6, 'Report generation is slow', 'Generating the quarterly HR report takes over 10 minutes.', 'In Progress', 'Normal', 5),
(9, 11, 'Login issue for new user', 'Fiona Funds cannot log into the new Wealth Management platform.', 'Open', 'High', 5);

-- Insert more Ticket Comments (starting from CommentID 5)
INSERT INTO TicketComments (TicketID, Comment, CreatedBy) VALUES
(2, 'Invoice has been resent to the customer.', 5), -- Comment on existing ticket
(4, 'The calendar sync issue seems to be related to a recent Google API update. Investigating.', 5), -- Comment on existing ticket
(5, 'Escalated to engineering to check the database query performance.', 5),
(6, 'Confirmed the issue is with the real-time data service. Restarting the service.', 5);

-- Update existing records to show data changes
UPDATE Leads SET Status = 'Contacted' WHERE LeadID = 2; -- Frank Stein
UPDATE Invoices SET Status = 'Paid' WHERE InvoiceID = 2; -- Innovate Inc. invoice
