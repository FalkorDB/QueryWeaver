"""Constants and benchmark data for the text2sql application."""

EXAMPLES = {
    "crm_usecase": [
        ("Which companies have generated the most revenue through closed deals, "
         "and how much revenue did they generate?"),
        "How many leads converted into deals over the last month",
        ("Which companies have open sales opportunities and active SLA agreements "
         "in place?"),
        ("Which high-value sales opportunities (value > $50,000) have upcoming meetings "
         "scheduled, and what companies are they associated with?"),
    ],
    "ERP_system": [
        # ("What is the total value of all purchase orders created in the last "
        #  "quarter?"),
        # ("Which suppliers have the highest number of active purchase orders, "
        #  "and what is the total value of those orders?"),
        "What is the total order value for customer Almo Office?",
        "Show the total amount of all orders placed on 11/24",
        "What's the profit for order SO2400002?",
        "List all confirmed orders form today with their final prices",
        "How many items are in order SO2400002?",
        # Product-Specific Questions
        "What is the price of Office Chair (part 0001100)?",
        "List all items with quantity greater than 3 units",
        "Show me all products with price above $20",
        "What's the total cost of all A4 Paper items ordered?",
        "Which items have the highest profit margin?",
        # Financial Analysis Questions
        "Calculate the total profit for this year",
        "Show me orders with overall discount greater than 5%",
        "What's the average profit percentage across all items?",
        "List orders with final price exceeding $700",
        "Show me items with profit margin above 50%",
        # Customer-Related Questions
        "How many orders has customer 100038 placed?",
        "What's the total purchase amount by Almo Office?",
        "List all orders with their customer names and contact details",
        "Show me customers with orders above $500",
        "What's the average order value per customer?",
        # Inventory/Stock Questions
        "Which items have zero quantity?",
        "Show me all items with their crate types",
        "List products with their packaging details",
        "What's the total quantity ordered for each product?",
        "Show me items with pending shipments",
    ],
}


BENCHMARK = [
    {
        "question": ("List all contacts who are associated with companies that have at "
                    "least one active deal in the pipeline, and include the deal stage."),
        "sql": ("SELECT DISTINCT c.contact_id, c.first_name, c.last_name, d.deal_id, "
               "d.deal_name, ds.stage_name FROM contacts AS c "
               "JOIN company_contacts AS cc ON c.contact_id = cc.contact_id "
               "JOIN companies AS co ON cc.company_id = co.company_id "
               "JOIN deals AS d ON co.company_id = d.company_id "
               "JOIN deal_stages AS ds ON d.stage_id = ds.stage_id "
               "WHERE ds.is_active = 1;"),
    },
    {
        "question": ("Which sales representatives (users) have closed deals worth more "
                    "than $100,000 in the past year, and what was the total value of "
                    "deals they closed?"),
        "sql": ("SELECT u.user_id, u.first_name, u.last_name, SUM(d.amount) AS "
               "total_closed_value FROM users AS u "
               "JOIN deals AS d ON u.user_id = d.owner_id "
               "JOIN deal_stages AS ds ON d.stage_id = ds.stage_id "
               "WHERE ds.stage_name = 'Closed Won' AND d.close_date >= "
               "DATE_SUB(CURDATE(), INTERVAL 1 YEAR) GROUP BY u.user_id "
               "HAVING total_closed_value > 100000;"),
    },
    {
        "question": ("Find all contacts who attended at least one event and were later "
                    "converted into leads that became opportunities within three months "
                    "of the event."),
        "sql": ("SELECT DISTINCT c.contact_id, c.first_name, c.last_name "
               "FROM contacts AS c "
               "JOIN event_attendees AS ea ON c.contact_id = ea.contact_id "
               "JOIN events AS e ON ea.event_id = e.event_id "
               "JOIN leads AS l ON c.contact_id = l.contact_id "
               "JOIN opportunities AS o ON l.lead_id = o.lead_id "
               "WHERE o.created_date BETWEEN e.event_date AND "
               "DATE_ADD(e.event_date, INTERVAL 3 MONTH);"),
    },
    {
        "question": ("Which customers have the highest lifetime value based on their "
                    "total invoice payments, including refunds and discounts?"),
        "sql": ("SELECT c.contact_id, c.first_name, c.last_name, "
               "SUM(i.total_amount - COALESCE(r.refund_amount, 0) - "
               "COALESCE(d.discount_amount, 0)) AS lifetime_value "
               "FROM contacts AS c "
               "JOIN orders AS o ON c.contact_id = o.contact_id "
               "JOIN invoices AS i ON o.order_id = i.order_id "
               "LEFT JOIN refunds AS r ON i.invoice_id = r.invoice_id "
               "LEFT JOIN discounts AS d ON i.invoice_id = d.invoice_id "
               "GROUP BY c.contact_id ORDER BY lifetime_value DESC LIMIT 10;"),
    },
    {
        "question": ("Show all deals that have involved at least one email exchange, "
                    "one meeting, and one phone call with a contact in the past six months."),
        "sql": ("SELECT DISTINCT d.deal_id, d.deal_name FROM deals AS d "
               "JOIN contacts AS c ON d.contact_id = c.contact_id "
               "JOIN emails AS e ON c.contact_id = e.contact_id "
               "JOIN meetings AS m ON c.contact_id = m.contact_id "
               "JOIN phone_calls AS p ON c.contact_id = p.contact_id "
               "WHERE e.sent_date >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH) "
               "AND m.meeting_date >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH) "
               "AND p.call_date >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH);"),
    },
    {
        "question": ("Which companies have the highest number of active support tickets, "
                    "and how does their number of tickets correlate with their total deal value?"),
        "sql": ("SELECT co.company_id, co.company_name, COUNT(st.ticket_id) AS active_tickets, "
               "SUM(d.amount) AS total_deal_value FROM companies AS co "
               "LEFT JOIN support_tickets AS st ON co.company_id = st.company_id "
               "AND st.status = 'Open' "
               "LEFT JOIN deals AS d ON co.company_id = d.company_id "
               "GROUP BY co.company_id ORDER BY active_tickets DESC;"),
    },
    {
        "question": ("Retrieve all contacts who are assigned to a sales rep but have not "
                    "been contacted via email, phone, or meeting in the past three months."),
        "sql": ("SELECT c.contact_id, c.first_name, c.last_name FROM contacts AS c "
               "JOIN users AS u ON c.owner_id = u.user_id "
               "LEFT JOIN emails AS e ON c.contact_id = e.contact_id "
               "AND e.sent_date >= DATE_SUB(CURDATE(), INTERVAL 3 MONTH) "
               "LEFT JOIN phone_calls AS p ON c.contact_id = p.contact_id "
               "AND p.call_date >= DATE_SUB(CURDATE(), INTERVAL 3 MONTH) "
               "LEFT JOIN meetings AS m ON c.contact_id = m.contact_id "
               "AND m.meeting_date >= DATE_SUB(CURDATE(), INTERVAL 3 MONTH) "
               "WHERE e.contact_id IS NULL AND p.contact_id IS NULL "
               "AND m.contact_id IS NULL;"),
    },
    {
        "question": ("Which email campaigns resulted in the highest number of closed deals, "
                    "and what was the average deal size for those campaigns?"),
        "sql": ("SELECT ec.campaign_id, ec.campaign_name, COUNT(d.deal_id) AS closed_deals, "
               "AVG(d.amount) AS avg_deal_value FROM email_campaigns AS ec "
               "JOIN contacts AS c ON ec.campaign_id = c.campaign_id "
               "JOIN deals AS d ON c.contact_id = d.contact_id "
               "JOIN deal_stages AS ds ON d.stage_id = ds.stage_id "
               "WHERE ds.stage_name = 'Closed Won' GROUP BY ec.campaign_id "
               "ORDER BY closed_deals DESC;"),
    },
    {
        "question": ("Find the average time it takes for a lead to go from creation to "
                    "conversion into a deal, broken down by industry."),
        "sql": ("SELECT ind.industry_name, AVG(DATEDIFF(d.close_date, l.created_date)) "
               "AS avg_conversion_time FROM leads AS l "
               "JOIN companies AS co ON l.company_id = co.company_id "
               "JOIN industries AS ind ON co.industry_id = ind.industry_id "
               "JOIN opportunities AS o ON l.lead_id = o.lead_id "
               "JOIN deals AS d ON o.opportunity_id = d.opportunity_id "
               "WHERE d.stage_id IN (SELECT stage_id FROM deal_stages "
               "WHERE stage_name = 'Closed Won') GROUP BY ind.industry_name "
               "ORDER BY avg_conversion_time ASC;"),
    },
    {
        "question": ("Which sales reps (users) have the highest win rate, calculated as "
                    "the percentage of their assigned leads that convert into closed deals?"),
        "sql": ("SELECT u.user_id, u.first_name, u.last_name, "
               "COUNT(DISTINCT d.deal_id) / COUNT(DISTINCT l.lead_id) * 100 AS win_rate "
               "FROM users AS u "
               "JOIN leads AS l ON u.user_id = l.owner_id "
               "LEFT JOIN opportunities AS o ON l.lead_id = o.lead_id "
               "LEFT JOIN deals AS d ON o.opportunity_id = d.opportunity_id "
               "JOIN deal_stages AS ds ON d.stage_id = ds.stage_id "
               "WHERE ds.stage_name = 'Closed Won' GROUP BY u.user_id "
               "ORDER BY win_rate DESC;"),
    },
]
